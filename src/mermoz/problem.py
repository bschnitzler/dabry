import h5py
from mdisplay.geodata import GeoData
from mpl_toolkits.basemap import Basemap
from pyproj import Proj

from mermoz.feedback import Feedback
from mermoz.integration import IntEulerExpl
from mermoz.wind import RankineVortexWind, UniformWind, DiscreteWind, LinearWind, RadialGaussWind, DoubleGyreWind, \
    PointSymWind
from mermoz.model import Model, ZermeloGeneralModel
from mermoz.stoppingcond import StoppingCond, TimedSC
from mermoz.misc import *

problems = {
    0: ['Three vortices', '3vor'],
    1: ['Linear wind', 'linear'],
    2: ['Honolulu Vancouver', 'honolulu-vancouver'],
    3: ['Double Gyre Li2020', 'double-gyre-li2020'],
    4: ['Double Gyre Kularatne2016', 'double-gyre-ku2016'],
    5: ['Point symmetric Techy2011', 'pointsym-techy2011'],
    6: ['Three obstacles', '3obs'],
    7: ['San-Juan Dublin Ortho', 'sanjuan-dublin-ortho'],
    8: ['Big Rankine vortex', 'big_rankine'],
    9: ['Four vortices', '4vor'],
    10: ['Dakar Natal', 'dakar-natal'],
}


class MermozProblem:
    """
    The Mermoz problem class defines the whole optimal control problem.

            min T
        x(0) = x_init
        x(T) = x_target
        x_dot(t) = v_a * s(t) + v_w(x(t))
        where s(t) is a control vector of unit norm
    """

    def __init__(self,
                 model: Model,
                 x_init,
                 x_target,
                 coords,
                 domain=None,
                 bl=None,
                 tr=None,
                 autodomain=True,
                 mask_land=True):
        self.model = model
        self.x_init = np.zeros(2)
        self.x_init[:] = x_init
        self.x_target = np.zeros(2)
        self.x_target[:] = x_target
        self.coords = coords

        # Domain bounding box corners
        if bl is not None:
            self.bl = np.zeros(2)
            self.bl[:] = bl
        else:
            self.bl = None
        if tr is not None:
            self.tr = np.zeros(2)
            self.tr[:] = tr
        else:
            self.tr = None

        self._geod_l = distance(self.x_init, self.x_target, coords=self.coords)

        self.bm = None

        self.descr = 'Problem'

        if not domain:
            if not autodomain:
                if self.bl is not None and self.tr is not None:
                    self.domain = lambda x: self.bl[0] < x[0] < self.tr[0] and self.bl[1] < x[1] < self.tr[1]
                else:
                    self.domain = lambda _: True
            else:
                # Bound computation domain on wind grid limits
                wind = self.model.wind
                if type(wind) == DiscreteWind:
                    self.bl = np.array((wind.x_min, wind.y_min))
                    self.tr = np.array((wind.x_max, wind.y_max))
                else:
                    w = 1.15 * self._geod_l
                    self.bl = (self.x_init + self.x_target) / 2. - np.array((w / 2., w / 2.))
                    self.tr = (self.x_init + self.x_target) / 2. + np.array((w / 2., w / 2.))
                if self.coords == COORD_GCS and mask_land:
                    factor = 1. if wind.units_grid == U_RAD else RAD_TO_DEG
                    self.bm = Basemap(llcrnrlon=factor * self.bl[0],
                                      llcrnrlat=factor * self.bl[1],
                                      urcrnrlon=factor * self.tr[0],
                                      urcrnrlat=factor * self.tr[1],
                                      projection='cyl', resolution='c')
                self.domain = lambda x: self.bl[0] < x[0] < self.tr[0] and self.bl[1] < x[1] < self.tr[1] and \
                                        (self.bm is None or not self.bm.is_land(factor * x[0], factor * x[1]))
        else:
            self.domain = domain

        self._feedback = None
        self.trajs = []

    def __str__(self):
        return str(self.descr)

    def load_feedback(self, feedback: Feedback):
        """
        Load a feedback law for integration

        :param feedback: A feedback law
        """
        self._feedback = feedback

    def integrate_trajectory(self,
                             x_init: ndarray,
                             stop_cond: StoppingCond,
                             max_iter=20000,
                             int_step=0.0001):
        """
        Use the specified discrete integration method to build a trajectory
        with the given control law. Store the integrated trajectory in
        the trajectory list.
        :param x_init: The initial state
        :param stop_cond: A stopping condition for the integration
        :param max_iter: Maximum number of iterations
        :param int_step: Integration step
        """
        if self._feedback is None:
            raise ValueError("No feedback provided for integration")
        sc = TimedSC(1.)
        sc.value = lambda t, x: stop_cond.value(t, x) or not self.domain(x)
        integrator = IntEulerExpl(self.model.wind,
                                  self.model.dyn,
                                  self._feedback,
                                  self.coords,
                                  stop_cond=sc,
                                  max_iter=max_iter,
                                  int_step=int_step)
        self.trajs.append(integrator.integrate(x_init))

    def eliminate_trajs(self, target, tol: float):
        """
        Delete trajectories that are too far from the objective point
        :param tol: The radius tolerance around the objective in meters
        """
        delete_index = []
        for k, traj in enumerate(self.trajs):
            keep = False
            for id, p in enumerate(traj.points):
                if np.linalg.norm(p - target) < tol:
                    keep = True
                    break
            if not keep:
                delete_index.append(k)
        for index in sorted(delete_index, reverse=True):
            del self.trajs[index]


class DatabaseProblem(MermozProblem):

    def __init__(self, wind_fpath, x_init=None, x_target=None, airspeed=AIRSPEED_DEFAULT):
        total_wind = DiscreteWind(interp='linear')
        total_wind.load(wind_fpath)
        print(f'Problem from database : {wind_fpath}')

        with h5py.File(wind_fpath, 'r') as f:
            coords = f.attrs['coords']
            print(coords)
            if x_init is None:
                print('Automatic parameters')
                bl = np.array((f['grid'][0, 0, 0], f['grid'][0, 0, 1]))
                tr = np.array((f['grid'][-1, -1, 0], f['grid'][-1, -1, 1]))
                offset = (tr - bl) * 0.1
                x_init = bl + offset
                x_target = tr - offset

        zermelo_model = ZermeloGeneralModel(airspeed, coords=coords)
        zermelo_model.update_wind(total_wind)
        super().__init__(zermelo_model, x_init, x_target, coords)


class IndexedProblem(MermozProblem):

    def __init__(self, i, seed=0):
        if i == 0:
            v_a = 23.
            coords = COORD_CARTESIAN

            factor = 1e6
            factor_speed = v_a

            x_init = factor * np.array([0., 0.])
            x_target = factor * np.array([1., 0.])

            bl = factor * np.array([-0.2, -1.])
            tr = factor * np.array([1.2, 1.])

            import csv
            with open('/home/bastien/Documents/work/mermoz/src/mermoz/.seeds/problem0/center1.csv', 'r') as f:
                reader = csv.reader(f)
                for k, row in enumerate(reader):
                    if k == seed:
                        omega1 = factor * np.array(list(map(float, row)))
                        break
            with open('/home/bastien/Documents/work/mermoz/src/mermoz/.seeds/problem0/center2.csv', 'r') as f:
                reader = csv.reader(f)
                for k, row in enumerate(reader):
                    if k == seed:
                        omega2 = factor * np.array(list(map(float, row)))
                        break
            with open('/home/bastien/Documents/work/mermoz/src/mermoz/.seeds/problem0/center3.csv', 'r') as f:
                reader = csv.reader(f)
                for k, row in enumerate(reader):
                    if k == seed:
                        omega3 = factor * np.array(list(map(float, row)))
                        break

            vortex1 = RankineVortexWind(omega1[0], omega1[1], factor * factor_speed * -1., factor * 1e-1)
            vortex2 = RankineVortexWind(omega2[0], omega2[1], factor * factor_speed * -0.8, factor * 1e-1)
            vortex3 = RankineVortexWind(omega3[0], omega3[1], factor * factor_speed * 0.8, factor * 1e-1)
            const_wind = UniformWind(np.array([0., 0.]))

            alty_wind = 3. * const_wind + vortex1 + vortex2 + vortex3
            total_wind = DiscreteWind()
            total_wind.load_from_wind(alty_wind, 101, 101, bl, tr, coords=coords)

            zermelo_model = ZermeloGeneralModel(v_a)
            zermelo_model.update_wind(total_wind)

            super(IndexedProblem, self).__init__(zermelo_model, x_init, x_target, coords)

        elif i == 1:
            v_a = 23.
            coords = COORD_CARTESIAN

            factor = 1e6
            x_init = factor * np.array([0., 0.])
            x_target = factor * np.array([1., 0.])

            gradient = np.array([[0., v_a / factor], [0., 0.]])
            origin = np.array([0., 0.])
            value_origin = np.array([0., 0.])

            bl = factor * np.array([-0.2, -1.])
            tr = factor * np.array([1.2, 1.])

            linear_wind = LinearWind(gradient, origin, value_origin)
            # total_wind = DiscreteWind()
            # total_wind.load_from_wind(linear_wind, 51, 51, bl, tr, coords)

            # Creates the cinematic model
            zermelo_model = ZermeloGeneralModel(v_a, coords=coords)
            zermelo_model.update_wind(linear_wind)

            super(IndexedProblem, self).__init__(zermelo_model, x_init, x_target, coords, bl=bl, tr=tr)

        elif i == 2:
            v_a = 23.
            coords = COORD_GCS

            total_wind = DiscreteWind(interp='linear')
            total_wind.load('/home/bastien/Documents/data/wind/windy/Vancouver-Honolulu-0.5.mz/data.h5')

            # Creates the cinematic model
            zermelo_model = ZermeloGeneralModel(v_a, coords=coords)
            zermelo_model.update_wind(total_wind)

            # Get problem domain boundaries
            bl = np.zeros(2)
            tr = np.zeros(2)
            bl[:] = total_wind.grid[1, 1]
            tr[:] = total_wind.grid[-2, -2]

            # Initial point
            gd = GeoData()
            offset = np.array([5., 5.])  # Degrees
            x_init = DEG_TO_RAD * (np.array(gd.get_coords('honolulu')) + offset)
            x_target = DEG_TO_RAD * (np.array(gd.get_coords('vancouver')) - offset)

            super(IndexedProblem, self).__init__(zermelo_model, x_init, x_target, coords)

        elif i == 3:
            v_a = 0.6

            sf = 1.

            x_init = sf * np.array((125., 125.))
            x_target = sf * np.array((375., 375.))
            bl = sf * np.array((-10, -10))
            tr = sf * np.array((510, 510))
            coords = COORD_CARTESIAN

            total_wind = DoubleGyreWind(0., 0., 500., 500., 1.)

            zermelo_model = ZermeloGeneralModel(v_a, coords=coords)
            zermelo_model.update_wind(total_wind)

            super(IndexedProblem, self).__init__(zermelo_model, x_init, x_target, coords, bl=bl, tr=tr)

        elif i == 4:
            v_a = 0.05

            sf = 1.

            x_init = sf * np.array((0.6, 0.6))
            x_target = sf * np.array((2.4, 2.4))
            bl = sf * np.array((0.5, 0.5))
            tr = sf * np.array((2.5, 2.5))
            coords = COORD_CARTESIAN

            total_wind = DoubleGyreWind(0.5, 0.5, 2., 2., pi * 0.02)

            zermelo_model = ZermeloGeneralModel(v_a, coords=coords)
            zermelo_model.update_wind(total_wind)

            super(IndexedProblem, self).__init__(zermelo_model, x_init, x_target, coords, bl=bl, tr=tr)

        elif i == 5:
            v_a = 23.
            sf = 1e6

            x_init = sf * np.array((0., 0.))
            x_target = sf * np.array((1., 0.))
            bl = sf * np.array((-0.1, -1.))
            tr = sf * np.array((1.1, 1.))
            coords = COORD_CARTESIAN

            gamma = v_a / sf * 1.
            omega = 0.
            total_wind = PointSymWind(sf * 0.5, sf * 0.3, gamma, omega)

            zermelo_model = ZermeloGeneralModel(v_a, coords=coords)
            zermelo_model.update_wind(total_wind)

            super(IndexedProblem, self).__init__(zermelo_model, x_init, x_target, coords, bl=bl, tr=tr)

        elif i == 6:

            v_a = 23.

            sf = 3e6

            x_init = sf * np.array((0., 0.))
            x_target = sf * np.array((1., 0.))
            bl = sf * np.array((-0.15, -1.15))
            tr = sf * np.array((1.15, 1.15))
            coords = COORD_CARTESIAN

            const_wind = UniformWind(np.array([1., 1.]))

            c1 = sf * np.array((0.5, 0.))
            c2 = sf * np.array((0.5, 0.1))
            c3 = sf * np.array((0.5, -0.1))

            obstacle1 = RadialGaussWind(c1[0], c1[1], sf * 0.1, 1 / 2 * 0.2, v_a * 5.)
            obstacle2 = RadialGaussWind(c2[0], c2[1], sf * 0.1, 1 / 2 * 0.2, v_a * 5.)
            obstacle3 = RadialGaussWind(c3[0], c3[1], sf * 0.1, 1 / 2 * 0.2, v_a * 5.)

            alty_wind = obstacle1 + obstacle2 + obstacle3 + const_wind

            total_wind = alty_wind  # DiscreteWind()

            zermelo_model = ZermeloGeneralModel(v_a, coords=coords)
            zermelo_model.update_wind(total_wind)

            super(IndexedProblem, self).__init__(zermelo_model, x_init, x_target, coords, bl=bl, tr=tr)

        elif i == 7:
            v_a = 23.
            coords = COORD_CARTESIAN
            total_wind = DiscreteWind()
            total_wind.load('/home/bastien/Documents/data/wind/ncdc/san-juan-dublin-flattened-ortho.mz/wind.h5')

            bl = total_wind.grid[0, 0]
            tr = total_wind.grid[-1, -1]

            gd = GeoData()
            proj = Proj(proj='ortho', lon_0=total_wind.lon_0, lat_0=total_wind.lat_0)

            point = np.array(gd.get_coords('San Juan', units='deg'))
            x_init = np.array(proj(*point))

            point = np.array(gd.get_coords('Dublin', units='deg'))
            x_target = np.array(proj(*point))

            zermelo_model = ZermeloGeneralModel(v_a, coords=coords)
            zermelo_model.update_wind(total_wind)

            # Creates the navigation problem on top of the previous model
            super(IndexedProblem, self).__init__(zermelo_model, x_init, x_target, coords, bl=bl, tr=tr)

        elif i == 8:
            v_a = 23.
            coords = COORD_CARTESIAN

            factor = 1e6
            factor_speed = v_a

            x_init = factor * np.array([0., 0.])
            x_target = factor * np.array([1., 0.])

            bl = factor * np.array([-0.2, -1.])
            tr = factor * np.array([1.2, 1.])
            omega = factor * np.array(((0.2, -0.2), (0.8, 0.2)))

            vortex = [
                RankineVortexWind(omega[0][0], omega[0][1], factor * factor_speed * -7., factor * 1.),
                RankineVortexWind(omega[1][0], omega[1][1], factor * factor_speed * -7., factor * 1.)
            ]
            const_wind = UniformWind(np.array([0., 0.]))

            alty_wind = const_wind + vortex[0] + vortex[1]
            # total_wind = DiscreteWind()
            # total_wind.load_from_wind(alty_wind, 101, 101, bl, tr, coords=coords)

            zermelo_model = ZermeloGeneralModel(v_a)
            zermelo_model.update_wind(alty_wind)

            super(IndexedProblem, self).__init__(zermelo_model, x_init, x_target, coords, bl=bl, tr=tr)

        elif i == 9:
            v_a = 23.
            coords = COORD_CARTESIAN

            factor = 1e6
            factor_speed = v_a

            x_init = factor * np.array([0., 0.])
            x_target = factor * np.array([1., 0.])

            bl = factor * np.array([-0.2, -1.])
            tr = factor * np.array([1.2, 1.])

            omega = factor * np.array(((0.5, 0.5),
                              (0.5, 0.2),
                              (0.5, -0.2),
                              (0.5, -0.5)))
            strength = factor * factor_speed * np.array([1., -1., 1.5, -1.5])
            radius = factor * np.array([1e-1, 1e-1, 1e-1, 1e-1])
            vortices = [RankineVortexWind(omega[i, 0], omega[i, 1], strength[i], radius[i]) for i in range(len(omega))]
            const_wind = UniformWind(np.array([0., 0.]))

            alty_wind = sum(vortices, const_wind)
            # total_wind = DiscreteWind()
            # total_wind.load_from_wind(alty_wind, 101, 101, bl, tr, coords=coords)

            zermelo_model = ZermeloGeneralModel(v_a)
            zermelo_model.update_wind(alty_wind)

            super(IndexedProblem, self).__init__(zermelo_model, x_init, x_target, coords, bl=bl, tr=tr)


        else:
            raise IndexError(f'No problem with index {i}')

        self.descr = problems[i][0]
        print(self.descr)