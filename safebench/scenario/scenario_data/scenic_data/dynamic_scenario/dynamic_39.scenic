'''The ego vehicle is entering the intersection; the adversarial vehicle comes from the right and turns left and stop, causing a near collision with the ego vehicle.'''
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

    # Execute a left turn maneuver
    do TurnBehavior(direction='left', target_speed=globalParameters.OPT_ADV_SPEED) until (
        distance to self < globalParameters.OPT_STOP_DISTANCE)

    # Stop abruptly to cause a near collision
    take SetBrakeAction(1.0)
    while True:
        take SetBrakeAction(1.0)
        wait

param OPT_ADV_SPEED = Range(0, 20)  # Controls the initial speed of the adversarial car.
param OPT_ADV_DISTANCE = Range(10, 30)  # Specifies the distance at which the car begins its maneuver.
param OPT_STOP_DISTANCE = Range(5, 15)  # The distance at which the adversarial vehicle stops abruptly.
intersection = Uniform(*filter(lambda i: i.is4Way or i.is3Way, network.intersections))
egoManeuver = Uniform(*intersection.maneuvers)
egoInitLane = egoManeuver.startLane
egoTrajectory = [egoInitLane, egoManeuver.connectingLane, egoManeuver.endLane]
egoSpawnPt = OrientedPoint in egoInitLane.centerline

ego = Car at egoSpawnPt,
    with regionContainedIn None,
    with blueprint EGO_MODEL
# Identifying the adjacent lane to the right for the Adversarial Agent and setting its spawn point
param OPT_GEO_Y_DISTANCE = Range(0, 30)
advLane = network.laneSectionAt(ego)._laneToRight.lane
IntSpawnPt = OrientedPoint following roadDirection from egoSpawnPt for globalParameters.OPT_GEO_Y_DISTANCE
projectPt = Vector(*advLane.centerline.project(IntSpawnPt.position).coords[0])
advHeading = advLane.orientation[projectPt]

# Spawn the Adversarial Agent
AdvAgent = Car at projectPt,
    with heading advHeading,
    with regionContainedIn None,
    with behavior AdvBehavior()