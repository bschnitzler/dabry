import csv
import datetime
import os
import sys

import asciitable
import h5py
import json

import numpy as np
import scipy.interpolate as itp
from numpy import sin, pi, cos
from math import atan2, asin
import matplotlib.pyplot as plt

sys.path.extend('/home/bastien/Documents/work/mdisplay/src/mdisplay/')
from mdisplay.misc import windy_cm

from mermoz.wind import DiscreteWind
from mermoz.misc import *

path_colors = ['b', 'g', 'r', 'c', 'm', 'y']


class TrajStats:

    def __init__(self,
                 length: float,
                 duration: float,
                 gs: ndarray,
                 crosswind: ndarray,
                 tgwind: ndarray,
                 vas: ndarray,
                 controls: ndarray,
                 dt: float,
                 dtarget: ndarray,
                 imax: int):
        self.imax = imax
        self.length = length
        self.duration = duration
        self.gs = np.zeros(imax+1)
        self.gs[:] = gs[:imax+1]
        self.cw = np.zeros(imax+1)
        self.cw[:] = crosswind[:imax+1]
        self.tw = np.zeros(imax+1)
        self.tw[:] = tgwind[:imax+1]
        self.vas = np.zeros(imax+1)
        self.vas[:] = vas[:imax+1]
        self.controls = np.zeros(imax+1)
        self.controls[:] = controls[:imax+1]
        self.dtarget = np.zeros(imax+1)
        self.dtarget[:] = dtarget[:imax+1]

        self.power = np.array(list(map(lambda v: 0.05 * v ** 3 + 1000 / v, self.vas)))
        self.energy = np.array(list(np.sum(self.power[:i]) for i in range(self.power.shape[0]))) * dt


class PostProcessing:

    def __init__(self, output_dir, traj_fn=None, wind_fn=None, param_fn=None):
        self.output_dir = output_dir
        self.traj_fn = traj_fn if traj_fn is not None else 'trajectories.h5'
        self.wind_fn = wind_fn if wind_fn is not None else 'wind.h5'
        self.param_fn = param_fn if param_fn is not None else 'params.json'
        self.analysis_fn = 'postproc.csv'

        self.x_init = np.zeros(2)
        self.x_target = np.zeros(2)
        with open(os.path.join(self.output_dir, self.param_fn), 'r') as f:
            pd = json.load(f)
            try:
                self.coords = pd['coords']
            except KeyError:
                print('[PP-Error] Missing coordinates type', file=sys.stderr)
                exit(1)

            try:
                self.x_init[:] = pd['x_init']
            except KeyError:
                print('[PP-Warn] No init point found')

            try:
                self.x_target[:] = pd['x_target']
            except KeyError:
                print('[PP-Warn] No target point found')

            success = False
            for name in ['va', 'airspeed']:
                try:
                    self.va = pd[name]
                    success = True
                except KeyError:
                    pass
            if not success:
                print('[PP-Warn] Airspeed not found in parameters, switching to default value')
                self.va = AIRSPEED_DEFAULT

        self.geod_l = distance(self.x_init, self.x_target, self.coords)

        wind_fp = os.path.join(self.output_dir, self.wind_fn)
        self.wind = DiscreteWind(interp='linear')
        self.wind.load(wind_fp)

        self.trajs = []

    def load(self):
        traj_fp = os.path.join(self.output_dir, self.traj_fn)
        f = h5py.File(traj_fp, "r")
        for k, traj in enumerate(f.values()):
            # Filter extremal fields
            if 'info' in traj.attrs.keys() and 'ef_' in traj.attrs['info']:
                continue
            _traj = {}
            _traj['data'] = np.zeros(traj['data'].shape)
            _traj['data'][:] = traj['data']
            _traj['controls'] = np.zeros(traj['controls'].shape)
            _traj['controls'][:] = traj['controls']
            _traj['ts'] = np.zeros(traj['ts'].shape)
            _traj['ts'][:] = traj['ts']

            _traj['type'] = traj.attrs['type']
            _traj['last_index'] = traj.attrs['last_index']
            _traj['interrupted'] = traj.attrs['interrupted']
            _traj['coords'] = traj.attrs['coords']
            _traj['label'] = traj.attrs['label']
            try:
                _traj['info'] = traj.attrs['info']
            except KeyError:
                # Backward compatibility
                _traj['info'] = ""
            if 'airspeed' in traj.keys():
                _traj['airspeed'] = np.zeros(traj['airspeed'].shape)
                _traj['airspeed'][:] = traj['airspeed']
            self.trajs.append(_traj)
        f.close()

    def stats(self, fancynormplot=False):
        fig, ax = plt.subplots(ncols=3, nrows=2, figsize=(12, 8))
        decorate(ax[0, 0], 'Marginal delay per length unit', 'Curvilinear abscissa (scaled)', '[h]')
        decorate(ax[0, 1], 'Power', 'Time (scaled)', '[W]')
        decorate(ax[0, 2], 'Energy spent', 'Time (scaled)', '[kWh]')
        decorate(ax[1, 0], 'Ground speed', 'Time (scaled)', '[m/s]', ylim=(0., 2. * self.va))
        decorate(ax[1, 1], 'Wind norm', 'Time (scaled)', '[m/s]', ylim=(0, 1.1 * self.va))
        decorate(ax[1, 2], 'Airspeed', 'Time (scaled)', '[m/s]')
        ax2 = ax[0, 2].twinx()
        ax2.tick_params(direction='in')
        ax2.set_ylabel('Distance to target (m)')
        tl, tu = None, None
        got_tu = False
        for k, traj in enumerate(self.trajs):
            ttl = traj['ts'][0]
            ttu = traj['ts'][traj['last_index']]
            if tl is None or ttl < tl:
                tl = ttl
            if not got_tu:
                if traj['type'] == 'optimal' and traj['info'].startswith('ef'):
                    tu = ttu
                    got_tu = True
                elif traj['type'] == 'optimal':
                    # RFT traj
                    tu = ttu
                    got_tu = True
            if not got_tu:
                if tu is None or ttu > tu:
                    tu = ttu
        for i, a in enumerate(ax):
            for j, b in enumerate(a):
                if i == 0 and j == 0:
                    continue
                b.set_xlim(tl, tu)
        entries = []
        ets = {}
        va_dur = {}
        for k, traj in enumerate(self.trajs):
            if 'rft' in traj['info'].lower():
                continue
            points = np.zeros(traj['data'].shape)
            points[:] = traj['data']
            ts = np.array(traj['ts'])
            if abs(ts[1] - ts[0]) < 1e-8:
                continue
            nt = traj['last_index']
            color = path_colors[k % len(path_colors)]
            tstats = self.point_stats(ts, points, last_index=nt)
            nt = tstats.imax + 2
            x = np.linspace(0, 1., nt - 1)
            ax[0, 0].plot(x, tstats.length * 1 / tstats.gs/3.6e3, label=f'{traj["info"]}', color=color)
            ax[0, 1].plot(ts[:nt - 1], tstats.power, color=color)
            ax[0, 2].plot(ts[:nt - 1], tstats.energy / 3.6e6, color=color)
            ax2.plot(ts[:nt - 1], tstats.dtarget, color=color, alpha=0.2)
            y = np.sqrt(tstats.cw ** 2 + tstats.tw ** 2)
            if fancynormplot:
                xx = np.linspace(0, nt - 1, 10 * (nt - 1))
                yy = itp.interp1d(x, y)(xx)
                ax[1, 1].scatter(xx, yy, c=windy_cm(yy / windy_cm.norm_max), s=0.5, color=color)
            else:
                ax[1, 1].plot(ts[:nt - 1], y, color=color)
            ax[1, 0].plot(ts[:nt - 1], tstats.gs, color=color)
            ax[1, 2].plot(ts[:nt - 1], tstats.vas, color=color)
            hours = int(tstats.duration / 3600)
            minutes = int((tstats.duration - 3600 * hours) / 60.)
            if int(hours) >= 1:
                timestamp = hours + minutes / 60
            else:
                timestamp = tstats.duration
            energy = np.mean(tstats.power) * tstats.duration
            ets[k] = (energy, tstats.duration)
            va_dur[k] = (tstats.vas[0], tstats.duration)
            e_kwh = energy / 3600000
            if int(e_kwh) >=1:
                energy = e_kwh

            line = ['',
                    f'{traj["label"]}',
                    f'{traj["type"] + " " + traj["info"]}',
                    f'{timestamp:.2f}',
                    f'{tstats.length / 1000:.2f}',
                    f'{np.mean(tstats.gs):>5.2f}',
                    f'{np.mean(tstats.vas):.2f}',
                    f'{np.mean(tstats.power):.1f}',
                    f'{energy:.1f}',
                    'x' if traj['interrupted'] else '']
            entries.append((tstats.duration, line))
        data = [['', '#', 'Name', 'Time', 'Length (km)', 'Mean GS (m/s)', 'Mean AS (m/s)',
                 'Mean power (W)', 'Energy (kWh)', 'Intr']] + \
               list(map(lambda x: x[1], sorted(entries, key=lambda x: x[0])))
        # asciitable.write(data, sys.stdout, Writer=asciitable.FixedWidthNoHeader)
        with open(os.path.join(self.output_dir, '..', '.post_proc', self.analysis_fn), 'w') as f:
            writer = csv.writer(f)
            writer.writerow([str(datetime.datetime.fromtimestamp(time.time())).split('.')[0]] + data[0][1:])
            writer.writerows(data[1:])
        ax[0, 0].legend(loc='center left', bbox_to_anchor=(0., 0.9))
        plt.show(block=False)
        fig, ax = plt.subplots()
        times = list(map(lambda x: x[1]/3.6e3, ets.values()))
        energies = list(map(lambda x: x[0]/3.6e6, ets.values()))
        colors = [path_colors[k % len(path_colors)] for k in range(len(energies))]
        ax.scatter(times, energies, c=colors)
        v_minp = (1000/(3*0.05)) ** (1/4)
        p_min = 0.05 * v_minp ** 3 + 1000 / v_minp
        decorate(ax, 'Energy vs. time', 'Time (h)', 'Energy (kWh)')
        ax.plot((0., 100), (0., 100 * p_min/1e3))
        plt.show()

        """
        fig, ax = plt.subplots()
        valist = []
        for k, traj in enumerate(self.trajs):
            ax.scatter(*va_dur[k], color=colors[k])
            valist.append(va_dur[k][0])
        valist = np.linspace(min(valist), max(valist), 100)
        ax.plot(valist, 2*self.geod_l / valist)
        plt.show()
        """

    def point_stats(self, ts, points, last_index=-1):
        """
        Return ground speed, crosswind and tangent wind for each node of the trajectory
        :param ts: ndarray (n,) of timestamps
        :param points: ndarray (n, 2) of trajectory points
        :return: a TrajStats object
        """
        if last_index < 0:
            n = points.shape[0]
        else:
            n = last_index
        # zero_ceil = np.mean(np.linalg.norm(points, axis=1)) * 1e-9
        gs = np.zeros(n - 1)
        cw = np.zeros(n - 1)
        tw = np.zeros(n - 1)
        vas = np.zeros(n - 1)
        controls = np.zeros(n - 1)
        dtarget = np.zeros(n - 1)
        duration = 0.
        t = ts[0]

        dtarget = np.array([distance(points[i], self.x_target, self.coords) for i in range(n - 1)])

        imax = n - 2
        for i in range(len(dtarget)):
            if dtarget[i]/self.geod_l < 5e-2:
                imax = i
                break

        length = float(np.sum([distance(points[i], points[i + 1], self.coords) for i in range(imax + 1)]))
        for i in range(n - 1):
            dt = ts[i + 1] - ts[i]
            p = np.zeros(2)
            p2 = np.zeros(2)
            p[:] = points[i]
            p2[:] = points[i + 1]
            corr_mat = EARTH_RADIUS * np.diag((np.cos(p[1]), 1.)) if self.coords == COORD_GCS else np.diag((1., 1.))
            delta_x = (p2 - p)
            dx_norm = np.linalg.norm(delta_x)
            e_dx = delta_x / dx_norm
            dx_arg = atan2(delta_x[1], delta_x[0])
            w = self.wind.value(t, p)
            w_norm = np.linalg.norm(w)
            w_arg = atan2(w[1], w[0])
            right = w_norm / self.va * sin(w_arg - dx_arg)
            gsv = corr_mat @ delta_x / dt
            u = atan2(*((gsv - w)[::-1]))
            v_a = np.linalg.norm(gsv - w)

            # def gs_f(uu, va, w, e_dx):
            #     return (np.array((cos(uu), sin(uu))) * va + w) @ e_dx
            #
            # u = max([dx_arg - asin(right), dx_arg + asin(right) - pi], key=lambda uu: gs_f(uu, self.va, w, e_dx))

            # gs[i] = gs_v = gs_f(u, self.va, w, e_dx)
            gs[i] = np.linalg.norm(gsv)
            cw[i] = np.cross(e_dx, w)
            tw[i] = e_dx @ w
            vas[i] = v_a
            controls[i] = u if self.coords == COORD_CARTESIAN else np.pi / 2. - u
            t = ts[i + 1]
            if i <= imax:
                duration += dt

        tstats = TrajStats(length, duration, gs, cw, tw, vas, controls, dt, dtarget, imax)
        return tstats


if __name__ == '__main__':
    pp = PostProcessing('/home/bastien/Documents/work/mermoz/output/example_solver-pa_linear_0')
    pp.stats(only_opti=True)
