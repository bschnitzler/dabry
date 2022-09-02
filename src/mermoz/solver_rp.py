import time
from math import atan2

from mermoz.problem import MermozProblem
from mermoz.rft import RFT
from mermoz.misc import *
from mermoz.feedback import FunFB
from mermoz.stoppingcond import TimedSC, DistanceSC


class SolverRP:
    """
    Minimum time trajectory planning solver
    using rough Reachability Front Tracking (RFT)
    to guess arrival time and arrival heading at destination
    and then Pontryagin's Maximum Principle to cheaply shoot extremal
    trajectories on previous parameters
    """

    def __init__(self,
                 mp: MermozProblem,
                 nx_rft,
                 ny_rft,
                 nt_rft,
                 nt_pmp=1000,
                 only_opti_extremals=False,
                 max_time=None):
        self.mp = mp
        self.x_init = np.zeros(2)
        self.x_init[:] = mp.x_init
        self.x_target = np.zeros(2)
        self.x_target[:] = mp.x_target
        self.nx_rft = nx_rft
        self.ny_rft = ny_rft
        self.nt_rft = nt_rft
        # Effective number of steps to reach target
        # Means nt_rft_eff is the smallest n such that
        # phi[n-1](x_target) > 0. and phi[n](x_target) < 0.
        self.nt_rft_eff = None

        self.nt_pmp = nt_pmp

        self.geod_l = distance(self.x_init, self.x_target, coords=self.mp.coords)

        if max_time is None:
            self.T = 1.2 * self.geod_l / mp.model.v_a
        else:
            self.T = max_time

        self.opti_ceil = self.geod_l / 50
        self.neighb_ceil = self.opti_ceil / 2.

        l = 2. * self.geod_l
        bl_rft = np.zeros(2)
        tr_rft = np.zeros(2)
        bl_rft[:] = mp.bl # (self.x_init + self.x_target) / 2. - np.array((l / 2., l / 2.))
        tr_rft[:] = mp.tr # (self.x_init + self.x_target) / 2. + np.array((l / 2., l / 2.))

        self.rft = RFT(bl_rft, tr_rft, self.T, nx_rft, ny_rft, nt_rft, mp, kernel='matlab')

        self.mp_dual = mp.dualize()

    def solve(self):
        print(f"Tracking reachability front ({self.nx_rft}x{self.ny_rft}x{self.nt_rft})... ")
        t_start = time.time()
        self.rft.compute()
        t_end = time.time()
        time_rft = t_end - t_start

        tu = self.rft.get_time(self.mp.x_target)
        tl = self.mp.model.wind.t_start
        self.mp_dual.load_feedback(FunFB(lambda x: self.rft.control(x, backward=True)))
        sc = DistanceSC(lambda x: self.mp.distance(x, self.mp_dual.x_target), self.mp._geod_l / 100.)
        traj = self.mp_dual.integrate_trajectory(self.mp_dual.x_init, sc, 1000, (tu - tl)/999, backward=True, t_init=tu)
        li = traj.last_index
        traj.timestamps[:li + 1] = traj.timestamps[:li + 1][::-1]
        traj.points[:li + 1] = traj.points[:li + 1][::-1]
        traj.type = TRAJ_OPTIMAL
        traj.info = 'RFT'
        #self.mp.trajs.append(self.rft.backward_traj(self.mp.x_target, self.mp.x_init, self.opti_ceil,
        #                                            self.T, self.mp.model, N_disc=1000))
        print(f"Done ({time_rft:.3f} s)")
