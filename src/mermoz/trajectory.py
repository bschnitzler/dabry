from .misc import *


class Trajectory:
    """
    The definition of a trajectory for the Mermoz problem
    """

    def __init__(self,
                 timestamps: ndarray,
                 points: ndarray,
                 controls: ndarray,
                 last_index: int,
                 optimal=False,
                 interrupted=False,
                 type=TRAJ_INT,
                 label=0,
                 coords=COORD_GCS):
        """
        :param timestamps: A list of timestamps (t_0, ..., t_N) at which the following values were computed
        :param points: A list of points ((x_0, y_0), ..., (x_N, y_N)) describing the trajectory
        :param controls: A list of controls (u_0, ..., u_N) applied to follow the previous trajectory
        :param last_index: The index of the last significant value
        :param optimal: Indicates if trajectory is optimal or not (for plotting)
        :param interrupted: Indicates if trajectory was interrupted during construction
        :param type: Gives the type of the trajectory : 'integral' or 'pmp'
        :param label: An optional integer label
        :param coords: Type of coordinates : 'cartesian or 'gcs'
        """
        self.timestamps = np.zeros(timestamps.shape)
        self.timestamps[:] = timestamps

        self.points = np.zeros(points.shape)
        self.points[:] = points

        self.controls = np.zeros(controls.shape)
        self.controls[:] = controls

        self.last_index = last_index
        self.interrupted = interrupted
        self.optimal = optimal
        self.type = type
        self.label = label
        self.coords = coords

    def get_final_time(self):
        return self.timestamps[self.last_index]

    def get_dt_stats(self):
        dt_list = np.zeros(self.timestamps.size - 1)
        dt_list[:] = self.timestamps[1:] - self.timestamps[:-1]
        return np.min(dt_list), np.max(dt_list), np.average(dt_list)


class AugmentedTraj(Trajectory):
    """
    Trajectory augmented by adjoint state
    """

    def __init__(self,
                 timestamps: ndarray,
                 points: ndarray,
                 adjoints: ndarray,
                 controls: ndarray,
                 last_index: int,
                 optimal=False,
                 interrupted=False,
                 type=TRAJ_INT,
                 label=0,
                 coords=COORD_GCS):
        """
        :param adjoints: A list of adjoint states ((p_x0, p_y0), ..., (p_xN, p_yN))
        """
        super().__init__(timestamps, points, controls, last_index, optimal=optimal, interrupted=interrupted, type=type,
                         label=label, coords=coords)
        self.adjoints = np.zeros(adjoints.shape)
        self.adjoints[:] = adjoints