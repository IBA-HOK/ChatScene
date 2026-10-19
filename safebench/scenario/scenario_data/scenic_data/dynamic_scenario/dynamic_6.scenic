'''The ego vehicle is turning left at an intersection; the adversarial pedestrian on the opposite sidewalk suddenly crosses the road from the right front and stops in the middle of the intersection.'''
Town = 'Town05'
param map = localPath(f'../maps/{Town}.xodr') 
param carla_map = Town
model scenic.simulators.carla.model
EGO_MODEL = "vehicle.lincoln.mkz_2017"

behavior AdvBehavior():
    do CrossingBehavior(ego, globalParameters.OPT_ADV_SPEED, globalParameters.OPT_ADV_DISTANCE) until (distance from self to egoTrajectory) < globalParameters.OPT_STOP_DISTANCE
    while True:
        take SetWalkingSpeedAction(0)

param OPT_ADV_SPEED = Range(0, 5)
param OPT_ADV_DISTANCE = Range(0, 15)
param OPT_STOP_DISTANCE = Range(0, 1)
intersection = Uniform(*filter(lambda i: i.is4Way or i.is3Way, network.intersections))
egoManeuver = Uniform(*filter(lambda m: m.type is ManeuverType.LEFT_TURN, intersection.maneuvers))
egoInitLane = egoManeuver.startLane
egoTrajectory = [egoInitLane, egoManeuver.connectingLane, egoManeuver.endLane]
egoSpawnPt = OrientedPoint in egoInitLane.centerline

ego = Car at egoSpawnPt,
    with regionContainedIn None,
    with blueprint EGO_MODEL
```scenic
# Parameters for the adversarial agent's position relative to the ego vehicle
param OPT_GEO_X_DISTANCE = Range(2, 10)
param OPT_GEO_Y_DISTANCE = Range(5, 20)

# Define the spawn point for the adversarial agent
# The agent is on the opposite sidewalk, entering from the right front.
# We calculate a point offset from the ego's spawn point.
# 'right front' implies positive Y (right) and positive X (front) in local coordinates relative to ego heading.
# However, since it's on the "opposite sidewalk", we need to ensure it's across the road.
# Using the ego's heading as reference for the offset.

IntSpawnPt = OrientedPoint following roadDirection from egoSpawnPt for globalParameters.OPT_GEO_Y_DISTANCE
SHIFT = globalParameters.OPT_GEO_X_DISTANCE @ globalParameters.OPT_GEO_Y_DISTANCE

# The agent is on the opposite sidewalk. 
# Assuming standard right-hand traffic, the opposite sidewalk is to the left of the oncoming lane, 
# which is to the left of the ego's lane. 
# However, the description says "entering from the right front". This usually implies the agent is 
# physically located to the right of the ego's path but moving towards it, or located on the 
# sidewalk that is to the right of the ego's current view but across the street? 
# Let's interpret "opposite sidewalk" as the sidewalk on the other side of the road from the ego.
# If ego is driving forward, the opposite sidewalk is to the Left (in a right-hand traffic system).
# But the description says "entering from the right front". This is a bit contradictory if strictly 
# geometric. Let's assume the agent is positioned on the sidewalk across the street, but the 
# "right front" refers to its relative position to the ego's future path or the visual entry point.
# Given the previous examples, we use offsets relative to the ego's heading.
# To be on the "opposite" side, we likely need a significant lateral offset.
# Let's place it to the left (negative Y in local frame if ego is right-hand traffic) or right?
# "Right front" usually means +X, +Y. "Opposite sidewalk" usually means across the road