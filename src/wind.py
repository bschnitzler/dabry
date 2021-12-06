from abc import ABC, abstractmethod
import numpy as np
from numpy import ndarray


class Wind(ABC):

    def __init__(self, value_func=None, d_value_func=None):
        """
        Builds a windfield which is a smooth vector field of space
        value_func Function taking a point in space (ndarray) and returning the
        wind value at the given point.
        d_value_func Function taking a point in space (ndarray) and returning the
        jacobian of the windfield at the given point.
        """
        self._value_func = value_func
        self._d_value_func = d_value_func

    def __add__(self, other):
        return Wind(value_func=lambda x: self._value_func(x) + other._value_func(x),
                    d_value_func=lambda x: self._d_value_func(x) + other._value_func(x))

    def __mul__(self, other):
        if isinstance(other, float):
            return Wind(value_func=other * self._value_func,
                        d_value_func=other * self._d_value_func)
        else:
            raise TypeError(f"Unsupported type for multiplication : {type(other)}")

    def value(self, x: ndarray) -> ndarray:
        return self._value_func(x)

    def d_value(self, x: ndarray) -> ndarray:
        return self._d_value_func(x)


class TwoSectorsWind(Wind):

    def __init__(self,
                 v_w1: float,
                 v_w2: float,
                 x_switch: float):
        """
        Wind configuration where wind is constant over two half-planes separated by x = x_switch. x-wind is null.

        :param v_w1: y-wind value for x < x_switch
        :param v_w2: y-wind value for x >= x_switch
        :param x_switch: x-coordinate for sectors separation
        """
        self.v_w1 = v_w1
        self.v_w2 = v_w2
        self.x_switch = x_switch

        self._value_func = lambda x: np.array([0, self.v_w1 * np.heaviside(self.x_switch - x[0], 0.)
                                               + self.v_w2 * np.heaviside(x[0] - self.x_switch, 0.)])
        self._d_value_func = lambda x: np.array([[0, 0],
                                                 [0, 0]])


class TSEqualWind(TwoSectorsWind):

    def __init__(self, v_w1, v_w2, x_f):
        """
        TwoSectorsWind but the sector separation is midway to the target

        :param x_f: Target x-coordinate.
        """
        super().__init__(v_w1, v_w2, x_f / 2)


class UniformWind(Wind):

    def __init__(self, wind_vector: ndarray):
        """
        :param wind_vector: Direction and strength of wind
        """
        self.wind_vector = wind_vector
        self._value_func = lambda x: self.value(x)
        self._d_value_func = lambda x: 0.

    def value(self, x):
        return self.wind_vector


class VortexWind(Wind):

    def __init__(self,
                 x_omega: float,
                 y_omega: float,
                 gamma: float):
        """
        A vortex from potential theory

        :param x_omega: x_coordinate of vortex center in m
        :param y_omega: y_coordinate of vortex center in m
        :param gamma: Circulation of the vortex in m^2/s. Positive is ccw vortex.
        """
        self.x_omega = x_omega
        self.y_omega = y_omega
        self.omega = np.array([x_omega, y_omega])
        self.gamma = gamma
        self._value_func = lambda x: self.value(x)

    def value(self, x):
        r = np.linalg.norm(x - self.omega)
        e_theta = np.array([-(x - self.omega)[1] / r,
                            (x - self.omega)[0] / r])
        return self.gamma / (2 * np.pi * r) * e_theta

    def d_value(self, x):
        r = np.linalg.norm(x - self.omega)
        x_omega = self.x_omega
        y_omega = self.y_omega
        return self.gamma / (2 * np.pi * r ** 4) * \
               np.array([[-2 * (x[0] - x_omega) * (x[1] - y_omega), (x[1] - y_omega) ** 2 - (x[0] - x_omega) ** 2],
                         [(x[1] - y_omega) ** 2 - (x[0] - x_omega) ** 2, -2 * (x[0] - x_omega) * (x[1] - y_omega)]])


class VortexUniformWind(VortexWind, UniformWind):

    def __init__(self, wind_vector, x_omega, y_omega, gamma):
        VortexWind.__init__(self, x_omega, y_omega, gamma)
        UniformWind.__init__(self, wind_vector)

    def value(self, x):
        return VortexWind.value(self, x) + UniformWind.value(self, x)

    def d_value(self, x):
        return VortexWind.d_value(self, x) + UniformWind.d_value(self, x)


class SourceWind(Wind):

    def __init__(self,
                 x_omega: float,
                 y_omega: float,
                 flux: float):
        """
        A source from potentiel theory

        :param x_omega: x_coordinate of source center in m
        :param y_omega: y_coordinate of source center in m
        :param flux: Flux of the source m^2/s. Positive is source, negative is well.
        """
        self.x_omega = x_omega
        self.y_omega = y_omega
        self.omega = np.array([x_omega, y_omega])
        self.flux = flux

    def value(self, x):
        r = np.linalg.norm(x - self.omega)
        e_r = (x - self.omega) / r
        return self.flux / (2 * np.pi * r) * e_r

    def d_value(self, x):
        raise ValueError("No derivative implemented for source wind")
