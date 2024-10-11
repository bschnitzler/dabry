import warnings
from abc import ABC, abstractmethod
from typing import Union, Optional

import numpy as np
from numpy import ndarray
from scipy.interpolate import RegularGridInterpolator

from dabry.misc import Utils, terminal

"""
obstacle.py
Obstacle definition as real-valued function of space for both
planar and spherical cases.

Copyright (C) 2021 Bastien Schnitzler 
(bastien dot schnitzler at live dot fr)

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program.  If not, see <https://www.gnu.org/licenses/>.
"""


class Obstacle(ABC):

    def __init__(self):
        pass

    @terminal
    def event(self, time: float, state_aug: ndarray):
        return self.value(time, state_aug[1:3])

    @abstractmethod
    def value(self, t: float, x: ndarray):
        """
        Return a negative value if within obstacle, positive if outside and zero at the border
        :param t: Time
        :param x: Position at which to get value (1D numpy array)
        :return: Obstacle function value
        """
        pass

    @abstractmethod
    def d_value(self, t: float, x: ndarray) -> ndarray:
        """
        Derivative of obstacle value function
        :param t: Time
        :param x: Position at which to get derivative (1D numpy array)
        :return: Gradient of obstacle function at point
        """
        pass

    def d_value_dt(self, t: float, x: ndarray) -> float:
        """
        Time derivative of obstacle
        :param t: Time
        :param x: State
        :return: Time derivative
        """
        return 0.


class WrapperObs(Obstacle):
    """
    Wrap an obstacle to work with appropriate units
    """

    def __init__(self, obs: Obstacle, scale_length: float, bl: ndarray, scale_time: float, time_origin: float):
        super().__init__()
        self.obs: Obstacle = obs
        self.scale_length = scale_length
        self.bl: ndarray = bl.copy()
        self.scale_time = scale_time
        self.time_origin = time_origin

    def value(self, t, x):
        return self.obs.value(self.time_origin + t * self.scale_time, self.bl + x * self.scale_length)

    def d_value(self, t, x):
        return self.obs.d_value(self.time_origin + t * self.scale_time, self.bl + x * self.scale_length)

    def __getattr__(self, item):
        if isinstance(self.obs, DiscreteObs):
            if item == 'values':
                return self.obs.values / self.scale_length
            if item == 'bounds':
                return self.obs.bounds / self.scale_length
        return self.obs.__getattribute__(item)


class CircleObs(Obstacle):
    """
    Circle obstacle defined by center and radius
    """

    def __init__(self, center: Union[ndarray, tuple[float, float]], radius: float):
        self.center = center.copy() if isinstance(center, ndarray) else np.array(center)
        self.radius = radius
        self._sqradius = radius ** 2
        super().__init__()

    def value(self, t, x: ndarray):
        return np.linalg.norm(x - self.center) - self.radius

    def d_value(self, t, x: ndarray) -> ndarray:
        return (x - self.center) / np.linalg.norm(x - self.center)


class FrameObs(Obstacle):
    """
    Rectangle obstacle acting as a frame
    """

    def __init__(self, bl: ndarray, tr: ndarray):
        self.bl = bl.copy()
        self.tr = tr.copy()
        self.center = 0.5 * (bl + tr)
        self.scaler = np.diag(1 / (0.5 * (self.tr - self.bl)))
        super().__init__()

    def value(self, t, x):
        return 1. - np.max(np.abs(np.dot(x[..., :2] - self.center, self.scaler)), -1)

    def d_value(self, t, x):
        xx = np.dot(x[..., :2] - self.center, self.scaler)
        c1 = np.dot(xx, np.array((1., 1.)))
        c2 = np.dot(xx, np.array((1., -1.)))
        g1 = np.dot(np.ones(xx.shape), np.diag((-self.scaler[0, 0], 0.)))
        g2 = np.dot(np.ones(xx.shape), np.diag((0., -self.scaler[1, 1])))
        g3 = np.dot(np.ones(xx.shape), np.diag((self.scaler[0, 0], 0.)))
        g4 = np.dot(np.ones(xx.shape), np.diag((0., self.scaler[1, 1])))
        return np.where((c1 > 0) * (c2 > 0), g1,
                        np.where((c1 > 0) * (c2 < 0), g2,
                                 np.where((c1 < 0) * (c2 < 0), g3,
                                          g4)))


class DiscreteObs(Obstacle):
    def __init__(self, values: ndarray, bounds: ndarray, no_diff=False, interp=None):
        super().__init__()

        if bounds.shape[0] != values.ndim:
            raise Exception(f'Incompatible shape for values and bounds: '
                            f'values has {len(values.shape)} dimensions '
                            f'so bounds must be of shape ({len(values.shape)}, 2) ({bounds.shape} given)')

        self.values = values.copy()
        self.bounds = bounds.copy()

        if values.ndim == 2:
            self.value = self._value_steady
            self.d_value = self._d_value_steady
            self.d_value_dt = self._d_value_dt_steady
            bl = bounds.T[0]
            tr = bounds.T[1]
            xx = np.linspace(bl[0], tr[0], values.shape[0])
            yy = np.linspace(bl[1], tr[1], values.shape[1])
            points = (xx, yy)

        else:
            self.value = self._value_unsteady
            self.d_value = self._d_value_unsteady
            self.d_value_dt = self._d_value_dt_unsteady
            self.t_start = bounds[0, 0]
            self.t_end = bounds[0, 1]
            bl = bounds.T[0]
            tr = bounds.T[1]
            tt = np.linspace(bl[0], tr[0], values.shape[0])
            xx = np.linspace(bl[1], tr[1], values.shape[1])
            yy = np.linspace(bl[2], tr[2], values.shape[2])
            points = (tt, xx, yy)

        if interp is None:
            # with Chrono('Building flow field spline interpolation'):
            self.interp = RegularGridInterpolator(points, values,
                                                  method='cubic' if not no_diff else 'linear',
                                                  bounds_error=False, fill_value=None)
        else:
            self.interp = interp

    def value(self, t: float, x: ndarray):
        pass

    def d_value(self, t: float, x: ndarray) -> ndarray:
        pass

    def d_value_dt(self, t, x):
        pass

    def _value_steady(self, _, x: ndarray):
        return self.interp(x)[0]

    def _value_unsteady(self, t, x):
        return self.interp(np.array((t, *tuple(x))))[0]

    def _d_value_steady(self, _, x):
        return np.stack((self.interp(x, nu=(1, 0)), self.interp(x, nu=(0, 1))), axis=-1)[0]

    def _d_value_unsteady(self, t, x):
        z = np.array((t, *tuple(x)))
        return np.stack((self.interp(z, nu=(0, 1, 0)), self.interp(z, nu=(0, 0, 1))), axis=-1)[0]

    def _d_value_dt_steady(self, _, x):
        return 0.

    def _d_value_dt_unsteady(self, t, x):
        z = np.array((t, *tuple(x)))
        return self.interp(z, nu=(1, 0, 0))[0]

    @classmethod
    def from_npz(cls, filepath, no_diff: Optional[bool] = None):
        obs = np.load(filepath, mmap_mode='r')
        kwargs = {}
        if no_diff is not None:
            kwargs['no_diff'] = no_diff
        return cls(obs['values'], obs['bounds'], **kwargs)

    @classmethod
    def from_obs(cls, obs: Obstacle, grid_bounds: Union[tuple[ndarray, ndarray], ndarray],
                 nx=51, ny=51, nt=25, **kwargs):
        """
        Create discrete obstacle from analytical obstacle.
        Similar to "from_ff" of the "DiscreteFF" class
        """
        # TODO : rewrite for time varying obstacles
        if isinstance(grid_bounds, tuple):
            if len(grid_bounds) != 2:
                raise ValueError('"grid_bounds" provided as a tuple must have two elements')
            grid_bounds = np.array(grid_bounds).transpose()

        if isinstance(grid_bounds, ndarray) and grid_bounds.shape != (2, 2):
            raise ValueError('"grid_bounds" provided as an array must have shape (2, 2)')

        bounds = grid_bounds.copy()
        shape = (nx, ny)
        spacings = (bounds[:, 1] - bounds[:, 0]) / (np.array(shape) - np.ones(bounds.shape[0]))
        values = np.zeros(shape)
        for i in range(nx):
            for j in range(ny):
                state = bounds[-2:, 0] + np.diag((i, j)) @ spacings[-2:]
                # TODO: modify this line
                values[i, j] = obs.value(0, state)

        return cls(values, bounds, **kwargs)


class WatershedObs(Obstacle):

    def __init__(self, center: ndarray, t_target: float, speed: float, a_tol: float):
        super(WatershedObs, self).__init__()
        self.center = np.array(center)
        self.t_target = t_target
        self.speed = speed
        self.a_tol = a_tol

    def value(self, t: float, x: ndarray):
        return np.max((self.a_tol, self.speed * (self.t_target - t))) ** 2 - np.sum(np.square(x - self.center))

    def d_value(self, t: float, x: ndarray) -> ndarray:
        return self.center - x

    def d_value_dt(self, t: float, x: ndarray) -> float:
        return -2 * self.speed * (self.t_target - t) if self.speed * (self.t_target - t) > self.a_tol else 0


class GreatCircleObs(Obstacle):

    # TODO: validate this class
    def __init__(self, p1, p2, z1=None, z2=None, autobox=False):

        # Cross product of p1 and p2 points TOWARDS obstacle
        # z1 and z2 are zone limiters
        X1 = np.array((np.cos(p1[0]) * np.cos(p1[1]),
                       np.sin(p1[0]) * np.cos(p1[1]),
                       np.sin(p1[1])))
        X2 = np.array((np.cos(p2[0]) * np.cos(p2[1]),
                       np.sin(p2[0]) * np.cos(p2[1]),
                       np.sin(p2[1])))
        if not autobox:
            self.z1 = z1
            self.z2 = z2
        else:
            delta_lon = Utils.angular_diff(p1[0], p2[0])
            delta_lat = p1[1] - p2[0]
            self.z1 = np.array((min(p1[0] - delta_lon / 2., p2[0] - delta_lon / 2.),
                                min(p1[1] - delta_lat / 2., p2[1] - delta_lat / 2.)))
            self.z2 = np.array((max(p1[0] + delta_lon / 2., p2[0] + delta_lon / 2.),
                                max(p1[1] + delta_lat / 2., p2[1] + delta_lat / 2.)))

        self.dir_vect = -np.cross(X1, X2)
        self.dir_vect /= np.linalg.norm(self.dir_vect)
        super().__init__()

    def value(self, _, x):
        if self.z1 is not None:
            if not Utils.in_lonlat_box(self.z1, self.z2, x):
                return 1.
        X = np.array((np.cos(x[0]) * np.cos(x[1]), np.sin(x[0]) * np.cos(x[1]), np.sin(x[1])))
        return X @ self.dir_vect

    def d_value(self, _, x):
        if self.z1 is not None:
            if not Utils.in_lonlat_box(self.z1, self.z2, x):
                return np.array((1., 1.))
        d_dphi = np.array((-np.sin(x[0]) * np.cos(x[1]), np.cos(x[0]) * np.cos(x[1]), 0))
        d_dlam = np.array((-np.cos(x[0]) * np.sin(x[1]), -np.sin(x[0]) * np.sin(x[1]), np.cos(x[1])))
        return np.array((self.dir_vect @ d_dphi, self.dir_vect @ d_dlam))


def discretize_obs(obs: Obstacle,
                   shape: tuple[int, int],
                   bl: Optional[ndarray] = None,
                   tr: Optional[ndarray] = None, no_diff=False):
    if not is_discrete_obstacle(obs):
        if bl is None or tr is None:
            raise Exception(f'Missing bounding box (bl, tr) to sample unbounded {obs}')
        return DiscreteObs.from_obs(obs, np.array((bl, tr)).transpose(), nx=shape[0], ny=shape[1], no_diff=no_diff)
    else:
        if shape[0] != obs.values.shape[0] or shape[1] != obs.values.shape[1]:
            warnings.warn(f'Grid shape {shape} differs from DiscreteObs native grid. Resampling not implemented yet: '
                          'Continuing with obstacle native grid')
        return obs


def save_obs(obs: Obstacle, filepath: str,
             shape: tuple[int, int],
             bl: Optional[ndarray] = None,
             tr: Optional[ndarray] = None):
    dobs = discretize_obs(obs, shape, bl, tr)
    np.savez(filepath, values=dobs.values, bounds=dobs.bounds)


def is_discrete_obstacle(obs: Obstacle):
    return isinstance(obs, DiscreteObs) or (isinstance(obs, WrapperObs) and isinstance(obs.obs, DiscreteObs))


def is_frame_obstacle(obs: Obstacle):
    return isinstance(obs, FrameObs) or (isinstance(obs, WrapperObs) and isinstance(obs.obs, FrameObs))


def is_circle_obstacle(obs: Obstacle):
    return isinstance(obs, CircleObs) or (isinstance(obs, WrapperObs) and isinstance(obs.obs, CircleObs))


def is_watershed_obstacle(obs: Obstacle):
    return isinstance(obs, WatershedObs) or (isinstance(obs, WrapperObs) and isinstance(obs.obs, WatershedObs))