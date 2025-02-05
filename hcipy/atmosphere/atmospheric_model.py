from __future__ import division

from ..optics import OpticalElement
from ..field import Field
from ..propagation import FresnelPropagator

import numpy as np
from scipy.special import gamma, kv

class AtmosphericLayer(OpticalElement):
	'''A single infinitely-thin atmospheric layer.

	This class serves as a base class for all atmospheric layers. Multiply
	atmospheric layers can be combined into an :class:`MultiLayerAtmosphere` which
	provides modelling of scintillation between layers.

	Parameters
	----------
	input_grid : Grid
		The grid on which the wavefront will be defined.
	Cn_squared : scalar
		The integrated value of Cn^2 for the layer.
	L0 : scalar
		The outer scale of the layer.
	velocity : scalar or array_like
		The velocity of the layer. If a scalar is given, its direction will be
		along x.
	height : scalar
		The height of the atmospheric layer above the ground.

	Attributes
	----------
	input_grid : Grid
		The grid on which the wavefront will be defined.
	t : scalar
		The current time.
	Cn_squared : scalar
		The integrated value of Cn^2 for the layer.
	L0 : scalar
		The outer scale of the phase structure function.
	velocity : array_like
		The two-dimensional velocity of the layer.
	height : scalar
		The height of the atmospheric layer above the ground.
	'''
	def __init__(self, input_grid, Cn_squared=None, L0=np.inf, velocity=0, height=0):
		self.input_grid = input_grid
		self.Cn_squared = Cn_squared
		self.L0 = L0

		self._velocity = None
		self.velocity = velocity

		self.height = height
		self._t = 0

	def evolve_until(self, t):
		'''Evolve the atmospheric layer until time `t`.

		Parameters
		----------
		t : scalar
			The time to which to evolve the atmospheric layer.
		'''
		raise NotImplementedError()

	def reset(self):
		'''Reset the phase screen.

		This will create a randomized uncorrelated phase screen.
		'''
		raise NotImplementedError()

	@property
	def t(self):
		'''The current time of the atmospheric layer.
		'''
		return self._t

	@t.setter
	def t(self, t):
		self.evolve_until(t)

	@property
	def Cn_squared(self):  # noqa: N802
		'''The integrated value of Cn^2 for the layer.
		'''
		return self._Cn_squared

	@Cn_squared.setter
	def Cn_squared(self, Cn_squared):  # noqa: N802
		raise NotImplementedError()

	@property
	def outer_scale(self):
		'''The outer scale of the phase structure function.
		'''
		return self._outer_scale

	@outer_scale.setter
	def outer_scale(self, L0):
		raise NotImplementedError()

	@property
	def L0(self):  # noqa: N802
		'''The outer scale of the phase structure function.
		'''
		return self.outer_scale

	@L0.setter
	def L0(self, L0):  # noqa: N802
		self.outer_scale = L0

	@property
	def velocity(self):
		'''The two-dimensional velocity of the layer.
		'''
		return self._velocity

	@velocity.setter
	def velocity(self, velocity):
		if np.isscalar(velocity):
			self._velocity = np.array([velocity, 0])
		else:
			self._velocity = np.array(velocity)

	def phase_for(self, wavelength):
		'''Get the phase screen in radians at a certain wavelength.

		Each atmospheric layer is modelled as an infinitely-thin phase screen.

		Parameters
		----------
		wavelength : scalar
			The wavelength at which to calculate the phase screen.
		'''
		raise NotImplementedError()

	@property
	def output_grid(self):
		return self.input_grid

	def forward(self, wf):
		wf = wf.copy()
		wf.electric_field *= np.exp(1j * self.phase_for(wf.wavelength))
		return wf

	def backward(self, wf):
		wf = wf.copy()
		wf.electric_field *= np.exp(-1j * self.phase_for(wf.wavelength))
		return wf

class MultiLayerAtmosphere(OpticalElement):
	'''A multi-layer atmospheric model.

	This :class:`OpticalElement` can model turbulence and scintillation effects
	due to atmospheric turbulence by propagating light through a series of
	infinitely-thin atmospheric phase screens at different altitudes. The distance
	between two phase screens can be propagated using Fresnel propagation, or using
	no :class:`Propagator`.

	Parameters
	----------
	layers : list of AtmosphericLayer objects
		The series of atmospheric layers in this model.
	scintillation : bool
		If True, then the distance between two phase screens is propagated using
		a :class:`FresnelPropagator`. Otherwise, no propagator will be used.
	'''
	def __init__(self, layers, scintillation=False, scintilation=None):
		# Retain backwards compatibility.
		if scintilation is not None:
			import warnings
			warnings.warn('Please use the correct spelling for scintillation.')

			scintillation = scintilation

		self.layers = layers
		self._scintillation = scintillation
		self._t = 0
		self._dirty = True

		self.calculate_propagators()

	def calculate_propagators(self):
		'''Recalculates the list of optical elements used for a propagation.

		This function is called automatically by other functions, but a recalculation
		can be forced by calling it explicitly.
		'''
		heights = np.array([l.height for l in self.layers])
		layer_indices = np.argsort(-heights)

		sorted_heights = heights[layer_indices]
		delta_heights = sorted_heights[:-1] - sorted_heights[1:]
		grid = self.layers[0].input_grid

		if self.scintillation:
			propagators = [FresnelPropagator(grid, h) for h in delta_heights]

		self.elements = []
		for i, j in enumerate(layer_indices):
			self.elements.append(self.layers[j])
			if self.scintillation and i < len(propagators):
				self.elements.append(propagators[i])

		if self.scintillation and sorted_heights[-1] > 0:
			self.elements.append(FresnelPropagator(grid, sorted_heights[-1]))

		self._dirty = False

	def reset(self):
		for l in self.layers:
			l.reset()

	@property
	def layers(self):
		'''A list of :class:`AtmosphericLayer` objects.
		'''
		return self._layers

	@layers.setter
	def layers(self, layers):
		self._layers = layers
		self._dirty = True

	def phase_for(self, wavelength):
		'''Get the unwrapped phase in radians for the atmosphere.

		Parameters
		----------
		wavelength : scalar
			The wavelength at which to calculate the phase screen.

		Returns
		-------
		Field
			The total unwrapped phase screen.
		'''
		if self.scintillation:
			raise ValueError('Cannot get the unwrapped phase for an atmosphere with scintillation.')

		unwrapped_phases = [layer.phase_for(wavelength) for layer in self.layers]

		return Field(np.sum(unwrapped_phases, axis=0), unwrapped_phases[-1].grid)

	@property
	def scintillation(self):
		'''Whether to include scintillation effects in the propagation.
		'''
		return self._scintillation

	@scintillation.setter
	def scintillation(self, scintillation):
		self._dirty = scintillation != self.scintillation
		self._scintillation = scintillation

	def evolve_until(self, t):
		'''Evolve all atmospheric layers to a time t.

		Parameters
		----------
		t : scalar
			The time to which to evolve the atmospheric layers.
		'''
		for l in self.layers:
			l.evolve_until(t)
		self._t = t

	@property
	def Cn_squared(self):  # noqa: N802
		'''The total Cn^2 value of the simulated atmosphere.
		'''
		return np.sum([l.Cn_squared for l in self.layers])

	@Cn_squared.setter
	def Cn_squared(self, Cn_squared):  # noqa: N802
		old_Cn_squared = self.Cn_squared
		for l in self.layers:
			l.Cn_squared = l.Cn_squared / old_Cn_squared * Cn_squared

	@property
	def outer_scale(self):
		'''The outer scale of all layers.
		'''
		return self.layers[0].outer_scale

	@outer_scale.setter
	def outer_scale(self, L0):
		for l in self.layers:
			l.outer_scale = L0

	@property
	def t(self):
		'''The current time.
		'''
		return self._t

	@t.setter
	def t(self, t):
		self.evolve_until(t)

	def forward(self, wavefront):
		if self._dirty:
			self.calculate_propagators()

		wf = wavefront.copy()
		for el in self.elements:
			wf = el.forward(wf)
		return wf

	def backward(self, wavefront):
		if self._dirty:
			self.calculate_propagators()

		wf = wavefront.copy()
		for el in reversed(self.elements):
			wf = el.backward(wf)
		return wf

def phase_covariance_von_karman(r0, L0):
	'''Return a Field generator for the phase covariance function for Von Karman turbulence.

	Parameters
	----------
	r0 : scalar
		The Fried parameter in meters.
	L0 : scalar
		The outer scale in meters.

	Returns
	-------
	Field generator
		The phase covariance Field generator.
	'''
	def func(grid):
		r = grid.as_('polar').r + 1e-10

		a = (L0 / r0)**(5 / 3)
		b = gamma(11 / 6) / (2**(5 / 6) * np.pi**(8 / 3))
		c = (24 / 5 * gamma(6 / 5))**(5 / 6)
		d = (2 * np.pi * r / L0)**(5 / 6)
		e = kv(5 / 6, 2 * np.pi * r / L0)

		return Field(a * b * c * d * e, grid)
	return func

def phase_structure_function_von_karman(r0, L0):
	'''Return a Field generator for the phase structure function for Von Karman turbulence.

	Parameters
	----------
	r0 : scalar
		The Fried parameter in meters.
	L0 : scalar
		The outer scale in meters.

	Returns
	-------
	Field generator
		The phase structure Field generator.
	'''
	def func(grid):
		r = grid.as_('polar').r + 1e-10

		a = (L0 / r0)**(5 / 3)
		b = 2**(1 / 6) * gamma(11 / 6) / np.pi**(8 / 3)
		c = (24 / 5 * gamma(6 / 5))**(5 / 6)
		d = gamma(5 / 6) / 2**(1 / 6)
		e = (2 * np.pi * r / L0)**(5 / 6)
		f = kv(5 / 6, 2 * np.pi * r / L0)

		return Field(a * b * c * (d - e * f), grid)
	return func

def power_spectral_density_von_karman(r0, L0):
	'''Return a Field generator for the power spectral density function for Von Karman turbulence.

	Parameters
	----------
	r0 : scalar
		The Fried parameter in meters.
	L0 : scalar
		The outer scale in meters.

	Returns
	-------
	Field generator
		The power spectral density Field generator.
	'''
	def func(grid):
		u = grid.as_('polar').r + 1e-10
		u0 = 2 * np.pi / L0

		res = 0.0229 * ((u**2 + u0**2) / (2 * np.pi)**2)**(-11 / 6.) * r0**(-5 / 3)
		res[u < 1e-9] = 0

		return Field(res, grid)
	return func

def Cn_squared_from_fried_parameter(r0, wavelength=500e-9):  # noqa: N802
	'''Calculate the integrated Cn^2 for a certain Fried parameter.

	Parameters
	----------
	r0 : scalar
		The Fried parameter in meters.
	wavelength : scalar
		The wavelength in meters at which the Fried parameter is measured (default: 500nm).

	Returns
	-------
	scalar
		The integrated Cn^2 value for the atmosphere.
	'''
	k = 2 * np.pi / wavelength
	return r0**(-5. / 3) / (0.423 * k**2)

def fried_parameter_from_Cn_squared(Cn_squared, wavelength=500e-9):  # noqa: N802
	'''Calculate the Fried parameter from the integrated Cn^2.

	Parameters
	----------
	r0 : scalar
		The integrated Cn^2 value for the atmosphere.
	wavelength : scalar
		The wavelength in meters at which to calculate the Fried parameter (default: 500nm).

	Returns
	-------
	scalar
		The Fried parameter in meters.
	'''
	k = 2 * np.pi / wavelength
	return (0.423 * Cn_squared * k**2)**(-3. / 5)

def seeing_to_fried_parameter(seeing, wavelength=500e-9):
	r'''Calculate the Fried parameter from the seeing FWHM.

	This uses :math:`\theta = 0.98 \lambda / r_0`, where :math:`\theta`
	is the FWHM of the seeing, :math:`\lambda` is the wavelength and
	:math:`r_0` is the Fried parameter.

	Parameters
	----------
	seeing : scalar
		The FWHM of the seeing in arcsec.
	wavelength : scalar
		The wavelength in meters at which the seeing is measured (default: 500nm).

	Returns
	-------
	scalar
		The Fried parameter in meters at the specified wavelength.
	'''
	return 0.98 * wavelength / np.radians(seeing / 3600)

def fried_parameter_to_seeing(r0, wavelength=500e-9):
	r'''Calculate the FWHM of the seeing from the Fried parameter.

	This uses :math:`\theta = 0.98 \lambda / r_0`, where :math:`\theta`
	is the FWHM of the seeing, :math:`\lambda` is the wavelength and
	:math:`r_0` is the Fried parameter.

	Parameters
	----------
	r0 : scalar
		The Fried parameter in meters.
	wavelength : scalar
		The wavelength in meters at which the Fried parameter is measured (default: 500nm).

	Returns
	-------
	scalar
		The FWHM of the seeing in arcsec at the specified wavelength.
	'''
	return np.degrees(0.98 * wavelength / r0) * 3600
