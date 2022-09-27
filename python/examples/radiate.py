"""Read lattice file and calculate radiation
"""
import logging
import copy
import xarray as xr

logging.basicConfig(level="DEBUG")
logger = logging.getLogger("thor_scsi")
print("\nlogger:\n", logger)
logger.setLevel("DEBUG")
# Levels: DEBUG, INFO, WARNING, ERROR, and CRITICAL.

from thor_scsi.factory import accelerator_from_config
from thor_scsi.utils.accelerator import instrument_with_radiators

from thor_scsi.lib import (
    ConfigType,
    ss_vect_tps,
    ss_vect_double,
    RadiationDelegate,
    RadiationDelegateKick,
    ObservedState
)
from thor_scsi.lib import phase_space_index_internal as phase_space_ind

import xarray as xr

logging.basicConfig(level="DEBUG")
from thor_scsi.factory import accelerator_from_config
from thor_scsi.utils.accelerator import instrument_with_radiators
from thor_scsi.utils.radiate import calculate_radiation

import os

import numpy as np
import scipy as sp

import numpy as np
import scipy as sp

import thor_scsi.lib as tslib

# from thor_scsi.utils.linalg import match_eigenvalues_to_plane_orig
from thor_scsi.utils.closed_orbit import compute_closed_orbit
from thor_scsi.utils.output import vec2txt, mat2txt, chop_array
from thor_scsi.utils.linear_optics import compute_M_diag, calculate_nu_symp


X_, Y_, Z_ = [
    tslib.spatial_index.X,
    tslib.spatial_index.Y,
    tslib.spatial_index.Z
]

x_, px_, y_, py_, ct_, delta_ = [
    tslib.phase_space_index_internal.x,
    tslib.phase_space_index_internal.px,
    tslib.phase_space_index_internal.y,
    tslib.phase_space_index_internal.py,
    tslib.phase_space_index_internal.ct,
    tslib.phase_space_index_internal.delta
]


import thor_scsi.lib as tslib

# from thor_scsi.utils.linalg import match_eigenvalues_to_plane_orig
from thor_scsi.utils.closed_orbit import compute_closed_orbit
from thor_scsi.utils.output import vec2txt, mat2txt
from thor_scsi.utils.linear_optics import compute_dispersion, compute_A_CS
from thor_scsi.utils.linalg import compute_A_prev, omega_block_matrix


X_ = 0
Y_ = 1
Z_ = 2


def chop_vec(vec, eps):
    for k in range(vec.size):
        if np.abs(vec[k]) < eps:
            vec[k] = 0e0
    return vec


def chop_mat(mat, eps):
    for k in range(mat[:, 0].size):
        chop_vec(mat[k, :], eps)
    return mat


def chop_cmplx_vec(vec, eps):
    for k in range(vec.size):
        [x, y] = [vec[k].real, vec[k].imag]
        if np.abs(x) < eps:
            x = 0e0
        if np.abs(y) < eps:
            y = 0e0
        vec[k] = complex(x, y)
    return vec


def chop_cmplx_mat(mat, eps):
    for k in range(mat[:, 0].size):
        chop_cmplx_vec(mat[k, :], eps)
    return mat


def acos2(sin, cos):
    # Calculate the normalised phase advance from the Poincaré map:
    #   Tr{M} = 2 cos(2 pi nu)
    # i.e., assuming mid-plane symmetry.
    # The sin part is used to determine the quadrant.
    mu = np.arccos(cos)
    if sin < 0e0:
        mu = 2e0*np.pi - mu
    return mu


def calculate_nu(M):
    tr = M.trace()
    # Check if stable.
    if tr < 2e0:
        calculate_nu(tr/2e0,  M[0][1])/(2e0*np.pi)
        return nu
    else:
        print("\ncalculate_nu: unstable\n")
        return float('nan')


def calculate_nus(n_dof, M):
    nus = np.zeros(n_dof, float)
    for k in range(n_dof):
        nus[k] = calculate_nu(M[2*k:2*k+2, 2*k:2*k+2])/(2e0*np.pi)
        if n_dof == 3:
            nus[2] = 1e0 - nus[2]
    return nus


def calculate_nu_symp(n_dof, M):
    # Calculate normalised phase advance from a symplectic periodic matrix.
    n = 2*dof
    I = np.identity(4)
    tr = np.zeros(n_dof, float)
    for k in range(n_dof):
        tr[k] = np.trace(M[2*k:2*k+2, 2*k:2*k+2])
    M4b4 = M[0:4, 0:4]
    [p1, pm1] = [np.linalg.det(M4b4-I), np.linalg.det(M4b4+I)]
    [po2, q] = [(p1-pm1)/16e0, (p1+pm1)/8e0 - 1e0]
    if tr[X_] > tr[Y_]:
        sgn = 1
    else:
        sgn = -1
    [x, y] = [-po2+sgn*np.sqrt(po2**2-q), -po2-sgn*np.sqrt(po2**2-q)]
    nu = []
    nu.extend([acos2(M[0][1], x)/(2e0*np.pi), acos2(M[2][3], y)/(2e0*np.pi)])
    if n_dof == 3:
        nu.append(1e0-acos2(M[4][5], tr[Z_]/2e0)/(2e0*np.pi))
    return np.array(nu)


def find_closest_nu(nu, w):
    min = 1e30
    for k in range(w.size):
        nu_k = acos2(w[k].imag, w[k].real)/(2e0*np.pi)
        diff =  np.abs(nu_k-nu)
        if diff < min:
            [ind, min] = [k, diff]
    return ind


def sort_eigen_vec(dof, nu, w):
    order = np.zeros(2*dof, int)
    for k in range(dof):
        order[2*k]   = find_closest_nu(nu[k], w)
        order[2*k+1] = find_closest_nu(1e0-nu[k], w)
    return order


t_dir = os.path.join(os.environ["HOME"], "Nextcloud", "thor_scsi")
# t_file = os.path.join(t_dir, "b3_tst.lat")
t_file = os.path.join(t_dir, "b3_sf_40Grad_JB.lat")

acc = accelerator_from_config(t_file)
print(" ".join([elem.name for elem in acc]))
print("\nC = ", np.sum([elem.getLength() for elem in acc]))

# b2 = acc.find("b2", 0)

energy = 2.5e9
# Just to test diffusion
# energy = 2.5

# Planes x y z
# from thor_scsi.lib import spatial_index
# print(spatial_index)

# cav.setVoltage(cav.getVoltage() * 1./2.)
# cav.setVoltage(0)
cav = acc.find("cav", 0)
print("acc cavity", repr(cav))
txt=\
    f"""Cavity info
frequency         {cav.getFrequency()/1e6} MHz",
voltage           {cav.getVoltage()/1e6} MV
harmonic number   {cav.getHarmonicNumber()}
    """
print(txt)

# cav.setVoltage(cav.getVoltage() * 1./2.)
# cav.setVoltage(0)
print("\nCavity", repr(cav))
txt = f"""\nCavity info:
  f [MHz] {1e-6*cav.getFrequency()}",
  V [MV]  {1e-6*cav.getVoltage()}
  h       {cav.getHarmonicNumber()}
"""
print(txt)

mbb = acc.find("mbb", 0)
print("{:s}: N = {:d}".
      format(mbb.name, mbb.getNumberOfIntegrationSteps()))

# Install radiators that radiation is calculated
rad_del_kicks = instrument_with_radiators(acc, energy=energy)

calc_config = tslib.ConfigType()

calc_config.radiation = True
calc_config.emittance = False
calc_config.Cavity_on = not True

print("\ncalc_config:\n [radiation, emittance, Cavity_on] = ",
      calc_config.radiation, calc_config.emittance, calc_config.Cavity_on)

calc_config.Energy = energy

if calc_config.Cavity_on == True:
    dof = 3
else:
    dof = 2

ps = tslib.ss_vect_double()
ps.set_zero()
ps[x_]     =  0e-3
ps[y_]     = -0e-3
ps[delta_] =  0e-6
print("\nps_0 = ", ps)
acc.propagate(calc_config, ps, 8, 8)
print("ps_1 = ", ps)

exit()

r = compute_closed_orbit(acc, calc_config, delta=0e0)
M = r.one_turn_map[:6, :6]
# print("\nM:\n" + mat2txt(M))
tune_x, tune_y, tune_long = calculate_nu_symp(3, M)

print(f"\n{tune_x=:.16f} {tune_y=:.16f} {tune_long=:.16f}")

exit()

# r = calculate_radiation(
#     acc, energy=2.5e9, calc_config=calc_config, install_radiators=True
# )

compute_M_diag(dof, M)

# exit()


use_tpsa = True
if not use_tpsa:
    ps = tslib.ss_vect_double()
    ps.set_zero()
    ps[tslib.phase_space_ind.x_] = 1e-3
else:
    ps = tslib.ss_vect_tps()
    ps.set_identity()


# First step:
#
# use closed orbit
# 1. calculate fix point and Poincarè Map M with damped system (i.e. radiation
#    on and cavity on (without dispersion in a second case)
# 2. diagonalise M = A $\Gamma$ A$^{-1}$
# 3. eigenvalues:
#        - complex part: tunes,
#        - real part: damping times  (refer equation)
#    use eigen values of symplectic matrix to identify the planes
# 4. propagate A, thin kick will create diffusion coeffs (don't forget to zero
#    them before calculation starts (sum it up afterwards




# print("Poincaré map calulation .... ")
# print("radiation OFF")
# print("start point")
# ps_start = copy.copy(ps)
# print(ps)
# print(ps.cst())



# calc_config.radiation = False
# acc.propagate(calc_config, ps, 0, 2000)
# print(ps)


print("\n\nradiation ON")
calc_config.radiation = True
calc_config.emittance = True
calc_config.Cavity_on = True
# ps_wr = copy.copy(ps_start)

r = compute_closed_orbit(acc, calc_config, delta=0e0)
M = r.one_turn_map[:6, :6]

# print("\nM:\n" + mat2txt(M))
print("\n\nFixed point:\n", vec2txt(r.x0))
tune_x, tune_y, tune_long = calculate_nu_symp(3, M)
print(f"\n{tune_x=:.16f} {tune_y=:.16f} {tune_long=:.16f}")

exit()

def extract_diffusion_coefficient():
    dD_rad = np.array([rk.getDiffusionCoefficientsIncrements() for rk in rad_del_kicks])
    print("Diffusion coefficients\n")
    print(dD_rad)
    D_rad = np.add.accumulate(dD_rad, axis=0)
    return D_rad


print(ps_wr)
acc.propagate(calc_config, ps_wr, 0, 2000)
print(ps_wr.cst())
print(ps_wr)
print("Effect of radiation")
print(ps_wr - ps)
print(ps_wr.cst() - ps.cst())


exit()
print(extract_diffusion_coefficient())
use_tpsa = False
if use_tpsa:
    # Inspect curly_H in
    for a_del in rad_del:
        name = a_del.getDelegatorName()
        idx = a_del.getDelegatorIndex()
        curly_H_x = a_del.getCurlydHx()
        txt = f"{name:10s} {idx:4d} curly_H_x {curly_H_x:5f}"
        print(txt)

    I = np.array([a_del.getSynchrotronIntegralsIncrements() for a_del in rad_del_kick])

    for a_del in rad_del_kick:
        name = a_del.getDelegatorName()
        idx = a_del.getDelegatorIndex()
        curly_H_x = a_del.getCurlydHx()
        dI = a_del.getSynchrotronIntegralsIncrements()
        D_rad = a_del.getDiffusionCoefficientsIncrements()

        txt = f"{name:10s} {idx:4d} curly_H_x {curly_H_x: 10.6e}"
        txt += "    dI " + ",".join(["{: 10.6e}".format(v) for v in dI])
        txt += "   "
        txt += "    D_rad" + ",".join(["{: 10.6e}".format(v) for v in D_rad])
        txt += "   "
        print(txt)
