# R256 — weight and support mechanics probe

This diagnostic integrates a rigid aggregate under gravity and contact forces. It addresses a specific distinction: a replayed fall can look convincing while its trajectory remains independent of mass, support and external force.

At 0.60 seconds the experiment disables the heel collision geometry. It does not prescribe the subsequent root pose, position or velocity. The intact and support-loss runs begin with identical states and physical parameters. A floor, friction, the remaining toe/sole contacts, and gravity determine the ensuing motion.

## Declared approximation

The body is a fixed-pose engineering surrogate with one free rigid body. Its total mass is an explicit input. Principal moments use a uniform ellipsoid approximation with semiaxes derived from the declared stature and build inputs. Visible capsules are collision/visual surrogates, not anatomical segments. One loaded shoe support represents the support-loss experiment.

The three paired cases are 1.55 m / 55 kg / build 0.90, 1.70 m / 75 kg / build 1.00, and 1.85 m / 95 kg / build 1.15. These are test inputs, not measured body subjects or a population model. Total mass already includes the body's contents; organ mass is never added on top.

The support event is prescribed, not a simulation of material fracture. This model has no balancing controller, protective step, articulated joints, active muscles, organ attachment, compliant tissue, or injury model. Its outputs cannot predict how a person would respond to a broken heel. It is not a source-human animation or an accepted realistic activity.

## Qualification

Eighteen bounded checks cover six paired support cases plus independent analytic controls:

- Settled vertical support equals the assigned weight, within 2%.
- Intact support remains upright within 0.03 radians.
- Removing heel contact produces an integrated response, and the removed heel contributes no subsequent contacts.
- With no gravity, removing support does not invent translation, rotation or velocity.
- In free space the same force produces the analytic velocity change for each of two masses.
- Free-fall acceleration is independent of mass.
- Halving the timestep keeps the pre-impact centre-of-mass height within 10 mm at 1.00 s.

The standard public GitHub Actions job uses Python 3.12 and exact wheel hashes. It produces six MJCF model files, six CSV traces, six replay JSON records, an animated GIF, a comparison PNG, a report and a SHA-256 manifest. The report binds execution to the source commit, public run and runner environment. Production acceptance is limited to these declared mechanics checks.

Run:

    python3 -m pip install --require-hashes -r rdte/r256-weight-support/requirements.txt
    python3 rdte/r256-weight-support/probe.py --out /tmp/r256-product

## Next connection to real bodies

A source-body implementation must derive a consistent articulated mass budget, collision geometry and inertial frames from the admitted body revision, then solve contact and balance with bounded joint torques. Morphology changes require regeneration of those properties and a fresh contact/controller qualification. Real organ response additionally needs registered geometry, physical material parameters, attachment/sliding constraints and independent dynamic evidence. This probe supplies none of those missing anatomical parameters.

Primary solver reference: https://mujoco.readthedocs.io/en/3.3.7/computation/

