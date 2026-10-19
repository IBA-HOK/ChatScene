'''The ego vehicle is turning right; the adversarial car (positioned behind on the right) suddenly accelerates and then decelerates.'''
Town = 'Town05'
param map = localPath(f'../maps/{Town}.xodr') 
param carla_map = Town
model scenic.simulators.carla.model
EGO_MODEL = "vehicle.lincoln.mkz_2017"

behavior AdvBehavior():
    while (distance to self) > 60:
        wait  # The adversarial car waits until it is within 60 meters of the ego vehicle.

    do FollowLaneBehavior(globalParameters.OPT_ADV_SPEED) until (
        distance to self < globalParameters.OPT_ADV_DISTANCE)

    # Suddenly accelerates
    take SetThrottleAction(globalParameters.OPT_THROTTLE)
    for _ in range(globalParameters.OPT_ACCEL_DURATION):
        wait

    # Then decelerates
    take SetBrakeAction(globalParameters.OPT_BRAKE)
    for _ in range(globalParameters.OPT_DECEL_DURATION):
        wait

param OPT_ADV_SPEED = Range(0, 20)  # Controls the initial speed of the adversarial car.
param OPT_ADV_DISTANCE = Range(0, 20)  # Specifies the distance at which the car begins its aggressive maneuver.
param OPT_THROTTLE = Range(0.5, 1)  # Aggressive throttle range.
param OPT_BRAKE = Range(0, 1)  # Determines the intensity of the braking.
param OPT_ACCEL_DURATION = Range(5, 20)  # Duration of the acceleration phase.
param OPT_DECEL_DURATION = Range(5, 20)  # Duration of the deceleration phase.
intersection = Uniform(*filter(lambda i: i.is4Way or i.is3Way, network.intersections))
egoManeuver = Uniform(*filter(lambda m: m.type is ManeuverType.RIGHT_TURN, intersection.maneuvers))
egoInitLane = egoManeuver.startLane
egoTrajectory = [egoInitLane, egoManeuver.connectingLane, egoManeuver.endLane]
egoSpawnPt = OrientedPoint in egoInitLane.centerline

ego = Car at egoSpawnPt,
    with regionContainedIn None,
    with blueprint EGO_MODEL
param OPT_GEO_BLOCKER_X_DISTANCE = Range(2, 8)
param OPT_GEO_BLOCKER_Y_DISTANCE = Range(-50, -15)
param OPT_GEO_X_DISTANCE = Range(-2, 2)
param OPT_GEO_Y_DISTANCE = Range(-6, -2)

RightBackSpawnPt = OrientedPoint following roadDirection from egoSpawnPt for globalParameters.OPT_GEO_BLOCKER_Y_DISTANCE
Blocker = Car right of RightBackSpawnPt by globalParameters.OPT_GEO_BLOCKER_X_DISTANCE,
    with heading RightBackSpawnPt.heading,
    with regionContainedIn None

SHIFT = globalParameters.OPT_GEO_X_DISTANCE @ globalParameters.OPT_GEO_Y_DISTANCE
AdvAgent = Car at Blocker offset along RightBackSpawnPt.heading by SHIFT,
    with heading RightBackSpawnPt.heading + 90 deg,
    with regionContainedIn None,
    with behavior AdvBehavior()