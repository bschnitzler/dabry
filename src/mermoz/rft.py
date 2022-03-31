import json
import os
import sys

import h5py
import numpy as np
from matplotlib import pyplot as plt
from numpy import ndarray
from math import sin, cos

from mermoz.misc import *
from mermoz.problem import MermozProblem


def upwind_diff(field, axis, delta):
    """
    Computes the derivative in the given direction with the given discretization step
    using an upwind scheme
    :param field: The field which derivative must be computed
    :param axis: The direction in which to compute the derivative
    :param delta: The discretization step
    :return: The derivated field
    """
    if axis not in [0, 1]:
        print("Only handles 2D fields")
        exit(1)
    nx, ny = field.shape
    res = np.zeros(field.shape)
    for i in range(1, nx - 1):
        for j in range(1, ny - 1):
            if axis == 0:
                if field[i - 1, j] < field[i, j] < field[i + 1, j]:
                    res[i, j] = (field[i, j] - field[i - 1, j]) / delta
                elif field[i - 1, j] > field[i, j] > field[i + 1, j]:
                    res[i, j] = (field[i + 1, j] - field[i, j]) / delta
                elif field[i - 1, j] <= field[i, j] >= field[i + 1, j]:
                    res[i, j] = (field[i + 1, j] - field[i - 1, j]) / (2 * delta)
                elif field[i - 1, j] >= field[i, j] <= field[i + 1, j]:
                    res[i, j] = 0
            else:
                # axis == 1
                if field[i, j - 1] < field[i, j] < field[i, j + 1]:
                    res[i, j] = (field[i, j] - field[i, j - 1]) / delta
                elif field[i, j - 1] > field[i, j] > field[i, j + 1]:
                    res[i, j] = (field[i, j + 1] - field[i, j]) / delta
                elif field[i, j - 1] <= field[i, j] >= field[i, j + 1]:
                    res[i, j] = (field[i, j + 1] - field[i, j - 1]) / (2 * delta)
                elif field[i, j - 1] >= field[i, j] <= field[i, j + 1]:
                    res[i, j] = 0
    for j in range(1, field.shape[1] - 1):
        res[0, j] = res[1, j]
        res[nx - 1, j] = res[nx - 2, j]
    for i in range(1, field.shape[0] - 1):
        res[i, 0] = res[i, 1]
        res[i, ny - 1] = res[i, ny - 2]
    res[0, 0] = res[1, 1]
    res[nx - 1, 0] = res[nx - 2, 1]
    res[0, ny - 1] = res[1, ny - 2]
    res[nx - 1, ny - 1] = res[nx - 2, ny - 2]
    return res


def wind_dot_phi(field, windfield, delta):
    """
    Computes the advection term "wind dot field" with the given discretization step
    using an upwind scheme
    From Sethian 6.45
    :param field: The field which derivative must be computed
    :param windfield: The windfield advecting the previous quantity
    :param delta: The discretization step
    :return: The gradient of the field
    """
    nx, ny = field.shape
    res = np.zeros(field.shape)
    for i in range(1, nx - 1):
        for j in range(1, ny - 1):
            d_mx = (field[i, j] - field[i - 1, j]) / delta
            d_px = (field[i + 1, j] - field[i, j]) / delta
            d_my = (field[i, j] - field[i, j - 1]) / delta
            d_py = (field[i, j + 1] - field[i, j]) / delta
            u_ijn = windfield[i, j, 0]
            v_ijn = windfield[i, j, 1]
            res[i, j] = max(u_ijn, 0.) * d_mx + min(u_ijn, 0.) * d_px + max(v_ijn, 0.) * d_my + min(v_ijn, 0.) * d_py

    for j in range(1, field.shape[1] - 1):
        res[0, j] = res[1, j]
        res[nx - 1, j] = res[nx - 2, j]
    for i in range(1, field.shape[0] - 1):
        res[i, 0] = res[i, 1]
        res[i, ny - 1] = res[i, ny - 2]
    res[0, 0] = res[1, 1]
    res[nx - 1, 0] = res[nx - 2, 1]
    res[0, ny - 1] = res[1, ny - 2]
    res[nx - 1, ny - 1] = res[nx - 2, ny - 2]
    return res


def central_diff(field, axis, delta):
    """
    Computes the derivative in the given direction with the given discretization step
    using a central difference scheme
    :param field: The field which derivative must be computed
    :param axis: The direction in which to compute the derivative
    :param delta: The discretization step
    :return: The derivated field
    """
    if axis not in [0, 1]:
        print("Only handles 2D fields")
        exit(1)
    nx, ny = field.shape
    res = np.zeros(field.shape)
    for i in range(1, nx - 1):
        for j in range(1, ny - 1):
            if axis == 0:
                res[i, j] = (field[i + 1, j] - field[i - 1, j]) / (2 * delta)
            else:
                # axis == 1
                res[i, j] = (field[i, j + 1] - field[i, j - 1]) / (2 * delta)
    for j in range(1, field.shape[1] - 1):
        res[0, j] = res[1, j]
        res[nx - 1, j] = res[nx - 2, j]
    for i in range(1, field.shape[0] - 1):
        res[i, 0] = res[i, 1]
        res[i, ny - 1] = res[i, ny - 2]
    res[0, 0] = res[1, 1]
    res[nx - 1, 0] = res[nx - 2, 1]
    res[0, ny - 1] = res[1, ny - 2]
    res[nx - 1, ny - 1] = res[nx - 2, ny - 2]
    return res


def grad(field, delta_x, delta_y, method='central'):
    """
    Computes the gradient of a field in a
    :param field: The field which gradient should be computed
    :param delta_x: The discretization step in the x-axis direction
    :param delta_y: The discretization step in the y-axis direction
    :param method: 'central' or 'upwind'
    :return: The gradient of the field
    """
    if method == 'central':
        diff0 = central_diff(field, 0, delta_x)
        diff1 = central_diff(field, 1, delta_y)
    elif method == 'upwind':
        diff0 = upwind_diff(field, 0, delta_x)
        diff1 = upwind_diff(field, 1, delta_y)
    else:
        print(f'Unknown method :{method}')
        exit(1)

    return np.stack((diff0, diff1), axis=2)


def norm_grad(field, delta_x, delta_y, method='central'):
    """
    Computes the norm of a field's gradient with the given method
    :param field: The field
    :param delta_x: The discretization step in the x-axis direction
    :param delta_y: The discretization step in the y-axis direction
    :param method: 'central' or 'upwind'
    :return: The norm of the gradient
    """
    if method == 'central':
        diff0 = central_diff(field, 0, delta_x)
        diff1 = central_diff(field, 1, delta_y)
    elif method == 'upwind':
        diff0 = upwind_diff(field, 0, delta_x)
        diff1 = upwind_diff(field, 1, delta_y)
    else:
        print(f'Unknown method :{method}')
        exit(1)
    return np.sqrt(diff0 ** 2 + diff1 ** 2)


class RFT:
    """
    Reachability front tracker
    """

    def __init__(self, bl, tr, max_time, nx, ny, mp: MermozProblem, x_init, nt=None, kernel='base',
                 method='sethian', coords=COORD_CARTESIAN):
        """
        :param bl: Grid bottom left point
        :param tr: Grid top right point
        :param max_time: Time window upper bound
        :param nx: Number of points in the x-axis direction
        :param ny: Number of points in the y-axis direction
        :param mp: The mermoz problem instance containing the analytic wind
        :param x_init: The problem starting point
        :param nt: Number of points in the time direction. Unused with matlab kernel.
        :param kernel: 'base' for Python implementation of level set methods or 'matlab'
        to use ToolboxLS (https://www.cs.ubc.ca/~mitchell/ToolboxLS)
        :param method: With 'base' kernel, select numerical scheme ('sethian' or 'lolla')
        :param coords: Coordinate type ('cartesian' or 'gcs')
        """
        ensure_coords(coords)
        self.coords = coords

        self.bl = np.zeros(2)
        self.bl[:] = bl
        self.tr = np.zeros(2)
        self.tr[:] = tr
        self.max_time = max_time

        self.nx = nx
        self.ny = ny
        self.nt = nt

        self.delta_x = (self.tr[0] - self.bl[0]) / (self.nx - 1)
        self.delta_y = (self.tr[1] - self.bl[1]) / (self.ny - 1)
        if self.nt is not None:
            self.delta_t = self.max_time / (self.nt - 1)
        else:
            self.delta_t = None

        self.mp = mp
        self.speed = mp.model.v_a
        self.x_init = np.zeros(2)
        self.x_init[:] = x_init
        self.wind = None
        self.phi = None

        self.ts = None
        self.flatten = False
        self.flatten_factor = EARTH_RADIUS

        self.method = method

        self.matlabLS_path = '/home/bastien/Documents/work/level-set/'

        self.t = 0
        self.kernel = kernel
        if self.kernel not in ['base', 'matlab']:
            print(f'Unknown kernel : {self.kernel}')
            exit(1)

    def compute(self):
        if self.kernel == 'base':
            # Setting up wind array
            for i in range(self.nx):
                for j in range(self.ny):
                    for k in range(self.nt):
                        self.wind[i, j, k, :] = self.mp.model.wind.value(
                            self.bl + np.array([self.delta_x * i, self.delta_y * j]))
            # Setting RF function to distance function at t=0
            for i in range(self.nx):
                for j in range(self.ny):
                    point = self.bl + np.array([self.delta_x * i, self.delta_y * j])
                    self.phi[i, j, 0] = np.linalg.norm(self.x_init - point) - 5e-3
            # Integrate
            for k in range(self.nt - 1):
                self.update_phi()
        elif self.kernel == 'matlab':
            # Matlab only processes 2D problem so first flatten the problem
            # if working in GCS
            if self.coords == COORD_GCS:
                self.toggle_flatten()

            # Give all arguments to matlab in a JSON file
            args = {
                "nx": self.nx,
                "ny": self.ny,
                "x_min": self.bl[0],
                "x_max": self.bl[0] + self.delta_x * (self.nx - 1),
                "y_min": self.bl[1],
                "y_max": self.bl[1] + self.delta_y * (self.ny - 1),
                "x_init": self.x_init[0],
                "y_init": self.x_init[1],
                "airspeed": self.mp.model.v_a,
                "max_time": self.max_time
            }
            with open(os.path.join(self.matlabLS_path, 'args.json'), 'w') as f:
                json.dump(args, f)

            # Give also the wind to the matlab script
            u = np.zeros((self.nx, self.ny))
            v = np.zeros((self.nx, self.ny))
            factor = 1 / EARTH_RADIUS
            for i in range(self.nx - 1):
                for j in range(self.ny - 1):
                    point = factor * np.array([self.bl[0] + i * self.delta_x, self.bl[1] + j * self.delta_y])
                    value = self.mp.model.wind.value(point)
                    u[i, j] = value[0]
                    v[i, j] = value[1]
            np.savetxt(os.path.join(self.matlabLS_path, 'input', 'u.txt'), u, delimiter=",")
            np.savetxt(os.path.join(self.matlabLS_path, 'input', 'v.txt'), v, delimiter=",")

            # Run matlab script
            os.system(f'matlab -sd {self.matlabLS_path} -batch "main; exit"')

            # Load matlab output in corresponding fields
            self.ts = np.genfromtxt(os.path.join(self.matlabLS_path, 'output', 'timesteps.txt'), delimiter=',')
            self.nt = self.ts.shape[0]
            self.nx, self.ny = np.genfromtxt(os.path.join(self.matlabLS_path, 'output', 'rff_0.txt'),
                                             delimiter=',').shape
            self.phi = np.zeros((self.nx, self.ny, self.nt))
            for k in range(self.nt):
                self.phi[:, :, k] = np.genfromtxt(os.path.join(self.matlabLS_path, 'output', f'rff_{k}.txt'),
                                                  delimiter=',')

            # Unflatten data if needed
            if self.coords == COORD_GCS:
                self.toggle_flatten()

    def toggle_flatten(self):
        """
        Change GCS coordinates to planar approximation considering
        parallels are great circles
        """
        if not self.flatten:
            factor = self.flatten_factor
            self.flatten = True
        else:
            factor = 1 / self.flatten_factor
            self.flatten = False
        self.bl[:] = factor * self.bl
        self.tr[:] = factor * self.tr

        self.delta_x *= factor
        self.delta_y *= factor

        self.x_init[:] = factor * self.x_init

    def update_phi(self):
        if self.method == 'lolla':
            # Copy current phi
            phi_cur = np.zeros(self.phi.shape[:-1])
            phi_cur[:] = self.phi[:, :, self.t]

            # Step 1 : build phi star
            phi_star = np.zeros(phi_cur.shape)
            phi_star[:] = phi_cur - self.delta_t / 2 * self.speed * norm_grad(phi_cur, self.delta_x, self.delta_y,
                                                                              method='central')

            # Step 2 : build phi star star
            phi_sstar = np.zeros(phi_cur.shape)
            phi_sstar[:] = phi_star - self.delta_t * np.einsum('ijk,ijk->ij', self.wind[:, :, self.t, :],
                                                               grad(phi_star, self.delta_x, self.delta_y,
                                                                    method='central'))

            # Step 3 : build next phi
            self.phi[:, :, self.t + 1] = phi_sstar - self.delta_t / 2. * self.speed * norm_grad(phi_sstar,
                                                                                                self.delta_x,
                                                                                                self.delta_y,
                                                                                                method='central')

        elif self.method == 'sethian':
            phi_cur = np.zeros(self.phi.shape[:-1])
            phi_cur[:] = self.phi[:, :, self.t]

            self.phi[:, :, self.t + 1] = phi_cur - self.delta_t * (
                    self.speed * norm_grad(phi_cur, self.delta_x, self.delta_y, method='central') + wind_dot_phi(
                phi_cur, self.wind[:, :, self.t, :], self.delta_x))

        else:
            print(f'Unknown update method for phi : {self.method}')

        self.t += 1

    def dump_rff(self, filepath):
        with h5py.File(os.path.join(filepath, 'rff.h5'), 'w') as f:
            nx, ny, nt = self.phi.shape
            f.attrs['coords'] = COORD_CARTESIAN
            dset = f.create_dataset('data', (nt, nx, ny), dtype='f8')
            dset[:, :, :] = self.phi.transpose((2, 0, 1))

            dset = f.create_dataset('ts', (nt,), dtype='f8')
            dset[:] = np.linspace(0., self.max_time, nt)

            dset = f.create_dataset('grid', (nx, ny, 2), dtype='f8')
            X, Y = np.meshgrid(self.bl[0] + self.delta_x * np.arange(self.nx),
                               self.bl[1] + self.delta_y * np.arange(self.ny), indexing='ij')
            dset[:, :, 0] = 1 / DEG_TO_RAD * X
            dset[:, :, 1] = 1 / DEG_TO_RAD * Y


def time_to_go(self,
               x_init: ndarray,
               x_end: ndarray):
    pass


if __name__ == '__main__':
    nx = 300
    ny = 300
    nts = 30
    delta_x = 1 / (nx - 1)
    delta_y = 1 / (ny - 1)
    delta_t = 0.1

    gradient = np.array([1.0, 2.0])
    field = np.zeros((nx, ny))
    norm_grad_field = np.zeros((nx, ny))
    d_field__d_x = np.zeros((nx, ny))
    d_field__d_y = np.zeros((nx, ny))
    for i in range(nx):
        for j in range(ny):
            x, y = delta_x * i, delta_y * j
            field[i, j] = sin(2 * np.pi * (x + 0.5 * y))
            d_field__d_x[i, j] = 2 * np.pi * cos(2 * np.pi * (x + 0.5 * y))
            d_field__d_y[i, j] = np.pi * cos(2 * np.pi * (x + 0.5 * y))
            norm_grad_field[i, j] = np.sqrt(
                2 * np.pi * cos(2 * np.pi * (x + 0.5 * y)) ** 2 + np.pi * cos(2 * np.pi * (x + 0.5 * y)) ** 2)

    fig, ax = plt.subplots(nrows=2, ncols=2)
    pos = ax[0, 0].imshow(field)
    ax[0, 0].set_title('$f$')
    fig.colorbar(pos, ax=ax[0, 0])
    pos = ax[0, 1].imshow(d_field__d_x)
    ax[0, 1].set_title('$\partial_x f$')
    fig.colorbar(pos, ax=ax[0, 1])
    pos = ax[1, 0].imshow((d_field__d_x - central_diff(field, 0, delta_x))[1:-1, 1:-1])
    ax[1, 0].set_title('Central diff delta')
    fig.colorbar(pos, ax=ax[1, 0])
    pos = ax[1, 1].imshow((d_field__d_x - upwind_diff(field, 0, delta_x))[1:-1, 1:-1])
    ax[1, 1].set_title('Upwind delta')
    # pos = ax[1].imshow((d_field__d_x - upwind_diff(field, 0, delta_x))[1:-1, 1:-1])
    fig.colorbar(pos, ax=ax[1, 1])

    print(f'Central max diff x    : {np.max(np.abs((d_field__d_x - central_diff(field, 0, delta_x))[1:-1, 1:-1]))}')
    print(
        f'Central max relative diff x: {np.max(np.abs((1 - central_diff(field, 0, delta_x) / d_field__d_x)[1:-1, 1:-1]))}')
    print(f'Upwind max diff x    : {np.max(np.abs((d_field__d_x - upwind_diff(field, 0, delta_x))[1:-1, 1:-1]))}')
    print(
        f'Upwind max relative diff x: {np.max(np.abs((1 - upwind_diff(field, 0, delta_x) / d_field__d_x)[1:-1, 1:-1]))}')

    print(f'Central max diff y    : {np.max(np.abs((d_field__d_y - central_diff(field, 1, delta_y))[1:-1, 1:-1]))}')
    print(
        f'Central max relative diff y: {np.max(np.abs((1 - central_diff(field, 1, delta_y) / d_field__d_y)[1:-1, 1:-1]))}')
    print(f'Upwind max diff y    : {np.max(np.abs((d_field__d_y - upwind_diff(field, 1, delta_y))[1:-1, 1:-1]))}')
    print(
        f'Upwind max relative diff y: {np.max(np.abs((1 - upwind_diff(field, 1, delta_y) / d_field__d_y)[1:-1, 1:-1]))}')

    plt.show()

    # origin + np.array([delta_x * i, delta_y * j])
    # field = np.array()
