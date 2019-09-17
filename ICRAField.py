import math
import random
import sys

import Box2D
import gym
import numpy as np
import pyglet
from gym import spaces
from gym.utils import EzPickle, colorize, seeding
from pyglet import gl

from Objects.Bullet import Bullet
from Objects.Robot import Robot
from Referee.BuffArea import AllBuffArea
from Referee.ICRAContactListener import ICRAContactListener
from Referee.ICRAMap import ICRAMap
from Referee.SupplyArea import SupplyAreas
from SupportAlgorithm.DetectCallback import detectCallback
from SupportAlgorithm.DataStructure import Action, RobotState

WINDOW_W = 1200
WINDOW_H = 1000

SCALE = 40.0        # Track scale
PLAYFIELD = 400/SCALE  # Game over boundary
FPS = 30
ZOOM = 2.7        # Camera zoom

SCAN_RANGE = 5  # m
COLOR_RED = (0.8, 0.0, 0.0)
COLOR_BLUE = (0.0, 0.0, 0.8)

ID_R1 = 0
ID_B1 = 1


def robotName2ID(robot_name):
    if robot_name == "robot_0":
        return ID_R1
    elif robot_name == "robot_1":
        return ID_B1


class ICRAField(gym.Env, EzPickle):

    __pos_safe = [
        [0.5, 0.5], [0.5, 2.0], [0.5, 3.0], [0.5, 4.5],  # 0 1 2 3
        [1.5, 0.5], [1.5, 3.0], [1.5, 4.5],             # 4 5 6
        [2.75, 0.5], [2.75, 2.0], [2.75, 3.0], [2.75, 4.5],  # 7 8 9 10
        [4.0, 1.75], [4.0, 3.25],                         # 11 12
        [5.25, 0.5], [5.25, 2.0], [5.25, 3.0], [5.25, 4.5],  # 13 14 15 16
        [6.5, 0.5], [6.5, 2.0], [6.5, 4.5],             # 17 18 19
        [7.5, 0.5], [7.5, 2.0], [7.5, 3.0], [7.5, 4.5]  # 20 21 22 23
    ]
    __id_pos_linked = [
        [1, 2, 3, 4], [0, 2, 3], [0, 1, 3, 5], [0, 1, 2, 6],
        [0, 7], [2, 9], [3, 10],
        [8, 9, 10, 4], [7, 9, 10, 11], [7, 8, 10, 5, 12], [7, 8, 9],
        [8, 14], [9, 15],
        [14, 15, 16, 17], [13, 15, 16, 18, 11, 11, 11, 11, 11], [
            13, 14, 16, 12, 12, 12, 12, 12], [13, 14, 15, 19],
        [13, 20], [14, 21], [16, 23],
        [21, 22, 23, 17], [20, 22, 23, 18], [20, 21, 23], [20, 21, 22, 19]
    ]

    def __init__(self):
        EzPickle.__init__(self)
        self.seed()
        self.__contactListener_keepref = ICRAContactListener(self)
        self.__world = Box2D.b2World(
            (0, 0), contactListener=self.__contactListener_keepref)
        self.__viewer = None
        self.__robots = {}
        self.__obstacle = None
        self.__area_buff = None
        self.__projectile = None
        self.__area_supply = None
        self.__callback_autoaim = detectCallback()

        self.reward = 0.0
        self.prev_reward = 0.0
        self.actions = {}
        self.state = {}

    def seed(self, seed=None):
        self.np_random, seed = seeding.np_random(seed)
        return [seed]

    def _destroy(self):
        for robot_name in self.__robots.keys():
            self.__robots[robot_name].destroy()
        self.__robots = {}
        if self.__obstacle:
            self.__obstacle.destroy()
        self.__obstacle = None
        if self.__projectile:
            self.__projectile.destroy()
        self.__projectile = None

    def reset(self):
        self._destroy()
        self.reward = 0.0
        self.prev_reward = 0.0
        self.t = 0.0

        self.__robots = {}

        random_index = random.randint(0, 23)
        #random_index = 5
        init_pos_0 = self.__pos_safe[random_index]
        init_pos_1 = self.__pos_safe[random.choice(
            self.__id_pos_linked[random_index])]

        self.__robots['robot_0'] = Robot(
            self.__world, 0, init_pos_0[0], init_pos_0[1],
            'robot_0', 0, 'red', COLOR_RED)
        self.__robots['robot_1'] = Robot(
            self.__world, 0, init_pos_1[0], init_pos_1[1],
            'robot_1', 1, 'blue', COLOR_BLUE)

        self.__obstacle = ICRAMap(self.__world)
        self.__projectile = Bullet(self.__world)
        self.__area_buff = AllBuffArea()
        self.__area_supply = SupplyAreas()

        self.state["robot_0"] = RobotState()
        self.state["robot_1"] = RobotState()

        self.actions["robot_0"] = None
        self.actions["robot_1"] = None
        self.reward = 0

        return init_pos_1
        # return self.step(None)[0]

    def __step_contact(self):
        contact_bullet_robot = self.__contactListener_keepref.collision_bullet_robot
        contact_bullet_wall = self.__contactListener_keepref.collision_bullet_wall
        contact_robot_wall = self.__contactListener_keepref.collision_robot_wall
        contact_robot_robot = self.__contactListener_keepref.collision_robot_robot
        for bullet, robot in contact_bullet_robot:
            self.__projectile.destroyById(bullet)
            if(self.__robots[robot].buffLeftTime) > 0:
                self.__robots[robot].loseHealth(25)
            else:
                self.__robots[robot].loseHealth(50)
        for bullet in contact_bullet_wall:
            self.__projectile.destroyById(bullet)
        for robot in contact_robot_wall:
            pass
            # self.robots[robot].loseHealth(2000)
        for robot in contact_robot_robot:
            self.__robots[robot].loseHealth(10)
        self.__contactListener_keepref.clean()

    def __step_action(self, robot_name, action: Action):
        # gas, rotate, transverse, rotate cloud terrance, shoot
        self.__robots[robot_name].moveAheadBack(action.v_t)
        self.__robots[robot_name].turnLeftRight(action.omega)
        self.__robots[robot_name].moveTransverse(action.v_n)
        if int(self.t * FPS) % (60 * FPS) == 0:
            self.__robots[robot_name].refreshReloadOppotunity()
        # if action[5] > 0.99:
            # self.robots[robot_name].addBullets()
            #action[5] = +0.0
        if action.shoot > 0.99 and int(self.t*FPS) % (FPS/5) == 1:
            if(self.__robots[robot_name].bullets_num > 0):
                angle, pos = self.__robots[robot_name].getGunAnglePos()
                self.__projectile.shoot(angle, pos)
                self.__robots[robot_name].bullets_num -= 1

    def _autoaim(self, robot_name):
        detected = {}
        scan_distance, scan_type = [], []
        self.state[robot_name].detect = False
        for i in range(-135, 135, 2):
            angle, pos = self.__robots[robot_name].getAnglePos()
            angle += i/180*math.pi
            p1 = (pos[0] + 0.3*math.cos(angle), pos[1] + 0.3*math.sin(angle))
            p2 = (pos[0] + SCAN_RANGE*math.cos(angle),
                  pos[1] + SCAN_RANGE*math.sin(angle))
            self.__world.RayCast(self.__callback_autoaim, p1, p2)
            scan_distance.append(self.__callback_autoaim.fraction)
            u = self.__callback_autoaim.userData
            if u in self.__robots.keys():
                scan_type.append(1)
                detected[u] = self.__callback_autoaim.point
                self.__robots[robot_name].setCloudTerrance(angle)
                self.state[robot_name].detect = True
            else:
                scan_type.append(0)
        self.state[robot_name].scan = [scan_distance, scan_type]

    def _update_robot_state(self, robot_name):
        self.state[robot_name].pos = self.__robots[robot_name].getPos()
        self.state[robot_name].health = self.__robots[robot_name].health
        self.state[robot_name].angle = self.__robots[robot_name].getAngle()
        self.state[robot_name].velocity = self.__robots[robot_name].getVelocity()
        self.state[robot_name].angular = self.__robots[robot_name].hull.angularVelocity

    def set_robot_action(self, robot_name, action):
        self.actions[robot_name] = action

    def step(self, action):
        ###### observe ######
        for robot_name in self.__robots.keys():
            self._autoaim(robot_name)
            self._update_robot_state(robot_name)

        ###### action ######
        self.set_robot_action("robot_0", action)
        for robot_name in self.__robots.keys():
            action = self.actions[robot_name]
            if action is not None:
                self.__step_action(robot_name, action)
            self.__robots[robot_name].step(1.0/FPS)
        self.__world.Step(1.0/FPS, 6*30, 2*30)
        self.t += 1.0/FPS

        ###### Referee ######
        self.__step_contact()
        self.__area_buff.detect(
            [self.__robots["robot_0"], self.__robots["robot_1"]], self.t)

        ###### reward ######
        step_reward = 0
        done = False
        # First step without action, called from reset()
        if self.actions["robot_0"] is not None:
            self.reward = (self.__robots["robot_0"].health -
                           self.__robots["robot_1"].health) / 4000.0

            #self.reward += 10 * self.t * FPS
            step_reward = self.reward - self.prev_reward
            if self.state["robot_0"].detect:
                step_reward += 1/3000

            if self.__robots["robot_0"].health <= 0:
                done = True
                #step_reward -= 1
            if self.__robots["robot_1"].health <= 0:
                done = True
                #step_reward += 1
            #self.reward += step_reward
            self.prev_reward = self.reward

        return self.state, step_reward, done, {}

    @staticmethod
    def get_gl_text(x, y):
        return pyglet.text.Label('0000', font_size=36, x=x, y=y,
                                 anchor_x='left', anchor_y='center',
                                 color=(255, 255, 255, 255))

    def render(self, mode='god'):
        if self.__viewer is None:
            from gym.envs.classic_control import rendering
            self.__viewer = rendering.Viewer(WINDOW_W, WINDOW_H)
            self.time_label = get_gl_text(20, WINDOW_H * 5.0 / 40.0)
            self.score_label = get_gl_text(520, WINDOW_H * 2.5 / 40.0)
            self.health_label = get_gl_text(520, WINDOW_H * 3.5 / 40.0)
            self.projectile_label = get_gl_text(520, WINDOW_H * 4.5 / 40.0)
            self.buff_left_time_label = get_gl_text(520, WINDOW_H * 5.5 / 40.0)
            self.transform = rendering.Transform()

        if "t" not in self.__dict__:
            return  # reset() not called yet

        zoom = ZOOM*SCALE
        scroll_x = 4.0
        scroll_y = 0.0
        angle = 0
        self.transform.set_scale(zoom, zoom)
        self.transform.set_translation(
            WINDOW_W/2 - (scroll_x*zoom*math.cos(angle) -
                          scroll_y*zoom*math.sin(angle)),
            WINDOW_H/4 - (scroll_x*zoom*math.sin(angle) + scroll_y*zoom*math.cos(angle)))

        self.__obstacle.draw(self.__viewer)
        if mode == 'god':
            for robot_name in self.__robots.keys():
                self.__robots[robot_name].draw(self.__viewer)
        elif mode == "fps":
            self.__robots["robot_0"].draw(self.__viewer)
            self.__robots["robot_1"].draw(self.__viewer)
        self.__projectile.draw(self.__viewer)

        arr = None
        win = self.__viewer.window
        if mode != 'state_pixels':
            win.switch_to()
            win.dispatch_events()

        win.clear()
        t = self.transform
        gl.glViewport(0, 0, WINDOW_W, WINDOW_H)
        t.enable()
        self.render_background()
        for geom in self.__viewer.onetime_geoms:
            geom.render()
        t.disable()
        self.render_indicators(WINDOW_W, WINDOW_H)
        win.flip()

        self.__viewer.onetime_geoms = []
        return arr

    def close(self):
        if self.__viewer is not None:
            self.__viewer.close()
            self.__viewer = None

    def render_background(self):
        gl.glBegin(gl.GL_QUADS)
        gl.glColor4f(0.4, 0.8, 0.4, 1.0)
        gl.glVertex3f(-PLAYFIELD, +PLAYFIELD, 0)
        gl.glVertex3f(+PLAYFIELD, +PLAYFIELD, 0)
        gl.glVertex3f(+PLAYFIELD, -PLAYFIELD, 0)
        gl.glVertex3f(-PLAYFIELD, -PLAYFIELD, 0)
        gl.glColor4f(0.4, 0.9, 0.4, 1.0)
        k = PLAYFIELD/20.0
        for x in range(-20, 20, 2):
            for y in range(-20, 20, 2):
                gl.glVertex3f(k*x + k, k*y + 0, 0)
                gl.glVertex3f(k*x + 0, k*y + 0, 0)
                gl.glVertex3f(k*x + 0, k*y + k, 0)
                gl.glVertex3f(k*x + k, k*y + k, 0)
        gl.glEnd()
        self.__area_buff.render(gl)
        self.__area_supply.render(gl)

    def render_indicators(self, W, H):
        self.time_label.text = "Time: {} s".format(int(self.t))
        self.score_label.text = "Score: %04i" % self.reward
        self.health_label.text = "health left Car0 : {} Car1: {} ".format(
            self.__robots["robot_0"].health, self.__robots["robot_1"].health)
        self.projectile_label.text = "Car0 bullets : {}, oppotunity to add : {}  ".format(
            self.__robots['robot_0'].bullets_num, self.__robots['robot_0'].opportuniy_to_add_bullets
        )
        self.buff_stay_time.text = 'Buff Stay Time: Red {}s, Blue {}s'.format(int(self.__area_buff.buffAreas[0].maxStayTime),
                                                                              int(self.__area_buff.buffAreas[1].maxStayTime))
        self.buff_left_time_label.text = 'Buff Left Time: Red {}s, Blue {}s'.format(int(self.__robots['robot_0'].buffLeftTime),
                                                                              int(self.__robots['robot_1'].buffLeftTime))
        self.time_label.draw()
        self.score_label.draw()
        self.health_label.draw()
        self.projectile_label.draw()
        self.buff_stay_time.draw()
        self.buff_left_time_label.draw()


if __name__ == "__main__":
    from pyglet.window import key, mouse
    # gas, rotate, transverse, rotate cloud terrance, shoot, reload
    #a = np.array([0.0, 0.0, 0.0, 0.0, 0.0, 0.0])
    #target = [0, 0]
    a = Action()

    def on_mouse_release(x, y, button, modifiers):
        x_low, x_high, y_low, y_high = 168, 1033, 249, 789
        width = x_high - x_low
        height = y_high - y_low
        x = (x - x_low) / width * 8.0
        y = (y - y_low) / height * 5.0
        target[0] = x
        target[1] = y

    def key_press(k, mod):
        global restart
        if k == key.ESCAPE:
            restart = True
        if k == key.W:
            a.v_t = +1.0
        if k == key.S:
            a.v_t = -1.0
        if k == key.Q:
            a.omega = +1.0
        if k == key.E:
            a.omega = -1.0
        if k == key.D:
            a.v_n = +1.0
        if k == key.A:
            a.v_n = -1.0
        if k == key.SPACE:
            a.shoot = +1.0

    def key_release(k, mod):
        if k == key.W:
            a.v_t = +0.0
        if k == key.S:
            a.v_t = -0.0
        if k == key.Q:
            a.omega = +0.0
        if k == key.E:
            a.omega = -0.0
        if k == key.D:
            a.v_n = +0.0
        if k == key.A:
            a.v_n = -0.0
        if k == key.SPACE:
            a.shoot = +0.0

    env = ICRAField()
    env.render()
    record_video = False
    if record_video:
        env.monitor.start('/tmp/video-test', force=True)
    env.__viewer.window.on_key_press = key_press
    env.__viewer.window.on_key_release = key_release
    #env.viewer.window.on_mouse_release = on_mouse_release
    #move = NaiveMove()
    while True:
        env.reset()
        total_reward = 0.0
        steps = 0
        restart = False
        s, r, done, info = env.step(a)
        while True:
            s, r, done, info = env.step(a)
            total_reward += r

            if steps % 200 == 0 or done:
                print("step {} total_reward {:+0.2f}".format(steps, total_reward))
            steps += 1

            # Faster, but you can as well call env.render() every time to play full window.
            if not record_video:
                env.render()
            if done or restart:
                break
    env.close()
