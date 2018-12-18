#!/usr/bin/env python3
"""
Example demonstrating how to communicate with Microsoft Robotic Developer
Studio 4 via the Lokarria http interface.

Author: Erik Billing (billing@cs.umu.se)

Updated by Ola Ringdahl 2014-09-11
Updated by Lennart Jern 2016-09-06 (converted to Python 3)
Updated by Filip Allberg and Daniel Harr 2017-08-30 (actually converted to Python 3)
Updated by Ola Ringdahl 2017-10-18 (added example code that use showMap)
Updated by Ola Ringdahl 2018-11-01 (fixed so that you can write the address with http://
    without getting a socket error. Added a function for converting (x,y) to (row,col))
"""
import sched

from multiprocessing import Pool
from bayes.Bayesian import Bayesian
from deliberativeLayer.cartographer.map_info import Cspace
from deliberativeLayer.cartographer.show_map import *
from deliberativeLayer.frontierBasedExploration.frontierCalculator import *
from deliberativeLayer.frontierBasedExploration.aStar import *
from reactiveLayer.pathTracking.obstacle_avoidance import detect_object_front
from reactiveLayer.sensing.robotMovement import *
from reactiveLayer.sensing.robotSensing import *
from reactiveLayer.pathTracking.purePursuit import *
import time

url = 'http://localhost:50000'
# HTTPConnection does not want to have http:// in the address apparently, so lest's remove it:
MRDS_URL = url[len("http://"):]
HEADERS = {"Content-type": "application/json", "Accept": "text/json"}
#s = sched.scheduler(time.time, time.sleep)

class UnexpectedResponse(Exception):
    pass


def calculate_distance(x1,y1,x2,y2):
    return (abs(x1-x2)**2+abs(y1-y2)**2)**0.5

"""Pythagoras theorem"""
def pythagoras_theorem(x, y):
    return sqrt((x ** 2) + (y ** 2))



def problem_on_path(path):

    for cell in path:
        x, y = (cell[0], cell[1])

        # for i in range(-1, 2):
        #    for j in range(-1, 2):

        if c_space.expanded_occupancy_grid[x][y] >= 0.2:
            print("Problem with object p>0.8 on path at (x,y): ", x, y)
            return True
        if math.isnan(c_space.expanded_occupancy_grid[x][y]):
            print("Problem with nan on path at:(x,y): ", x, y)
            c_space.occupancy_grid[x][y] = 0.5
            return True


"""Get the next goal point from the robot's position from a fixed look-a-head distance"""


def get_filtered_path(path, pos):

    minDistance = 100
    location = 0
    if path:
        for i in range(len(path)):
            # Get the coordinate on the top of the stack
            p = path[len(path) - i - 1]
            # Caculate the x and y distance from the actual
            # position to the carrot point
            dx = p[0] - pos[0]
            dy = p[1] - pos[1]
            # Calculate the distance
            h = pythagoras_theorem(dx, dy)
            # Update the location for the path coordinate
            # corresponding to the minimal distance
            if h < minDistance:
                minDistance = h
                location = i + 1

        # Pop everyting before this location
        for i in range(location):
            path.pop()

        return path

    else:
        print("Stack failed")




if __name__ == '__main__':

    showGUI = True  # set this to False if you run in putty

    # Max grid value
    maxVal = 15
    cell_size = 1
    path = []
    path_follower = PurePursuit()

    print('Sending commands to MRDS server', MRDS_URL)

    c_space = Cspace(-60, -60, 60, 50, cell_size)
    bayes_map = Bayesian(c_space.occupancy_grid, cell_size)
    map = ShowMap(c_space.grid_nr_rows, c_space.grid_nr_cols, showGUI, cell_size)
    robot_sensing = robotSensing()
    frontier_calculator = Frontier_calculator(20)
    path_planner = PathPlanner()
    pure_pursuit = PurePursuit()
    linear_speed = 1
    look_ahead_distance = 0.75/cell_size
    #pool = Pool(1)

    try:
        print('Telling the robot to go straight ahead.')
        response = post_speed(0, 0)

        while(1):

            #####################################
            # C_SPACE & EXPANDED C_SPACE UPDATE #
            #####################################

            # Get all the laser readout values starting from
            # the one with angle 0 to 270 (in meters)
            laser_scan_values = robot_sensing.get_laser_scan()

            # Get all the laser angles starting from 0 to 270
            laser_angles = robot_sensing.get_laser_angles()

            # Converts the car's (x, y) position to (row, col) coordinate in the grid
            pose = get_pose()
            curr_pos = pose['Pose']['Position']

            # Covert the vehicles' current position to coordinates
            robot_coord = pos_to_grid(curr_pos['X'], curr_pos['Y'], c_space.x_min, c_space.y_max, cell_size)
            robot_row = robot_coord[0]
            robot_col = robot_coord[1]

            # Retrieve the angles needed to calculate
            orientation = get_orientation()

            # Calculate the coordinates laser point readings

            sensor_readout_coordinates = robot_sensing.get_sensor_readout_coordinates(robot_coord,
                 laser_scan_values['Echoes'], laser_angles, orientation, cell_size)

            # Get all the Bresenham lines
            bresenham_lines = robot_sensing.get_bresenham_lines(robot_coord, sensor_readout_coordinates)

            # Calculate the probability for each cell in each Bresenham line based
            # on a laser sensor model
            for bresenham_line in bresenham_lines:
                bayes_map.bayes_handler(bresenham_line, robot_row, robot_col, c_space.get_grid_nr_rows(),
                                        c_space.get_grid_nr_cols())

            # Calculate the expanded grid used to get the paths
            c_space.calculate_expanded_occupancy_grid()

            ##########################
            # Calculates a new path when old one i followed or object detected
            ##########################

            if not path or problem_on_path(path):

                print("Calculating a new path")

                robot_coord = pos_to_grid(curr_pos['X'], curr_pos['Y'], c_space.x_min, c_space.y_max, cell_size)

                # Stop the vehicle
                post_speed(0, 0)

                # Calculate frontiers based on the current evidential grid
                frontiers = frontier_calculator.find_frontiers(c_space, robot_coord)

                if not frontiers:
                    # Stop the vehicle
                    post_speed(0, 0)
                    print("No frontier left to visit...")


                #If no frontiers found, decrese the minium points required until frontier detected
                #while not frontiers or (frontier_calculator.min_num_frontier_points == 2):
                #    frontier_calculator.change_frontier_attr()
                #    frontiers = frontier_calculator.find_frontiers(c_space, robot_coord)

                #    if frontier_calculator.min_num_frontier_points == 2 and len(frontiers) == 0:
                #        print("Explored as much as possible, no more frontiers to be found for minimal val")
                #        post_speed(0.5, 0)
                #frontier_calculator.change_frontier_attr()

                f = frontiers[0]
                #print("Goal:", f)
                f1 = math.floor(f[0])
                f2 = math.floor(f[1])
                goal = (f1, f2)

                robot_row = math.floor(robot_coord[0])
                robot_col = math.floor(robot_coord[1])
                start = (robot_row, robot_col)

                came_from, cost_so_far = path_planner.a_star_search(start, goal, c_space)
                path = path_planner.reconstruct_path(came_from, start, goal)

                #robot_coord = pos_to_grid(curr_pos['X'], curr_pos['Y'], c_space.x_min, c_space.y_max, cell_size)

                #path = get_filtered_path(path, robot_coord)

                #Update to complete history of paths taken, only use for figures
                #map.update_complete_path(path)



                # Set the vehicle to point in the right direction from the beginning
                pure_pursuit.init_orientation(path, look_ahead_distance, robot_coord, True)

            if pure_pursuit.is_correct_angle(path, look_ahead_distance, robot_coord):
                pass
            else:
                map.updateMap(c_space.occupancy_grid, maxVal, robot_row, robot_col, orientation, frontiers, path)
                continue


            if path:

                shit = [sensor_readout_coordinates[150], sensor_readout_coordinates[135],
                        sensor_readout_coordinates[120]]
                shit_2 = [laser_scan_values['Echoes'][150], laser_scan_values['Echoes'][135],
                          laser_scan_values['Echoes'][120]]
                object_detected = detect_object_front(path[len(path) - 1], shit, shit_2, cell_size)

                carrot_coordinate = pure_pursuit.get_carrot_point(path, robot_coord, look_ahead_distance)

                if carrot_coordinate:
                    # Transform coordinates system to vehicle coordinate system
                    vcs = pure_pursuit.tranform_to_vcs(robot_coord, carrot_coordinate)

                    # Calculate the curvature of the circular arc
                    curvature = pure_pursuit.calculate_curvature(vcs[0], vcs[1])

                    # Calculate angular speed
                    angularSpeed = curvature * linear_speed

                    # Apply angular and linear speed to the vehicle
                    post_speed(angularSpeed, linear_speed)
                #else:
                #    post_speed(0, 0)

            map.updateMap(c_space.occupancy_grid, maxVal, robot_row, robot_col, orientation, frontiers, path)


    except UnexpectedResponse as ex:
        print('Unexpected response from server when sending speed commands:', ex)


