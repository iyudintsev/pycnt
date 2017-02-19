from math import sqrt

import numpy as np
from numpy import linalg as la

from config import k_bond, mass
from particle import Particle, NodeParticle, Node
from error import NanotubeOverflow, NanotubeUnfilled

SQRT3_6 = sqrt(3) / 6
SQRT3_3 = SQRT3_6 * 2
coeff1_3 = 1. / 3


class Nanotube(object):
    def __init__(self, nan_id, total_num):
        self.nan_id = nan_id
        self.total_num = total_num
        self.num = 0
        self.particles = []
        self.nodes = []
        self.filled = False

        """ bonding """
        self.k_bond = k_bond
        self._bond_energy = 0

        """ MD """
        self._m = 1. / mass

    """ Create Particle """

    def create_particle(self, r):
        if self.num >= self.total_num:
            raise NanotubeOverflow("Nanotube {0}: total number = {1}".format(self.nan_id, self.total_num))
        particle_id = self.total_num * self.nan_id + self.num
        self.particles.append(Particle(r, particle_id))
        self.num += 1
        if self.num == self.total_num:
            self.create_nodes()
            self.filled = True

    """ Create Nodes """

    def create_node(self, index):
        r1 = self.particles[index].r
        r2 = self.particles[index+1].r
        dr = r2 - r1
        a, b, c = dr
        x0, y0, z0 = r1
        if c < 1e-16:
            c = 1e-15 if c > 0 else -1e-15
        z = z0 - (a * (1 - x0) + b * (1 - y0)) / c
        rx = np.array([1, 1, z])
        rx *= 1e-7 / la.norm(rx)
        ry = np.cross(dr, rx)
        ry *= 1e-7 / la.norm(ry)
        sign = -1 if index % 2 else 1
        node = Node(NodeParticle(r1 + sign * SQRT3_3 * rx),
                    NodeParticle(r1 + sign * (-SQRT3_6 * rx + .5 * ry)),
                    NodeParticle(r1 + sign * (-SQRT3_6 * rx - .5 * ry)), )
        self.nodes.append(node)

    def create_nodes(self):
        if not self.num == self.total_num:
            stat = self.total_num - self.num
            raise NanotubeUnfilled("Nanotube {0}: need to add {1} particles".format(self.nan_id, stat))
        for index in xrange(self.num - 1):
            self.create_node(index)
        penult_r = self.particles[self.num - 3].r
        last_r = self.particles[self.num - 1].r
        penult_node = self.nodes[self.num - 3]
        last_node = Node(*[NodeParticle(last_r + (penult_node[num].r - penult_r)) for num in xrange(3)])
        self.nodes.append(last_node)
        self.calc_all_distances()

    """ Distance Calculation """

    @staticmethod
    def get_index(index):
        if index == 0:
            return 1, 2
        if index == 1:
            return 2, 0
        if index == 2:
            return 0, 1

    def calc_distances(self, index):
        node1 = self.nodes[index]
        for diff in (0, 1):
            node2 = self.nodes[index+diff]
            for num in xrange(3):
                r0 = node1[num].r
                dr = [la.norm(r0 - node2[ind].r) for ind in self.get_index(num)]
                # print diff
                # print num
                # print dr
                if diff == 0:
                    node1[num].current_dist = dr
                if diff == 1:
                    node2[num].next_dist = dr

    def calc_all_distances(self):
        for index in xrange(self.num - 1):
            self.calc_distances(index)

    """ Bonding Force Calculation """

    def bonding_force(self, p1, p2, x0):
        dr = p1.r - p2.r
        dr_norm = la.norm(dr)
        f = - self.k_bond * (dr_norm - x0) / dr_norm * dr
        p1.f_bond += f
        p2.f_bond -= f

    def calc_force(self, index, next_node=False):
        node0 = self.nodes[index]
        node1 = node0 if not next_node else self.nodes[index+1]
        for num in xrange(3):
            p = node0[num]
            dist = p.current_dist if not next_node else p.next_dist
            for n, i in enumerate(self.get_index(num)):
                self.bonding_force(p, node1[i], dist[n])

    def calc_bonding_forces(self):
        for node in self.nodes:
            for p in node:
                p.f_bond = np.array([0., 0., 0.])

        for index in xrange(self.num - 1):
            self.calc_force(index)
            self.calc_force(index, next_node=True)

        self.calc_force(self.num - 1)

    """ Bonding Energy Calculation """

    def bonding_energy(self, p1, p2, x0):
        dr = p1.r - p2.r
        dr_norm = la.norm(dr)
        dx = (dr_norm - x0)
        self._bond_energy += .5 * self.k_bond * dx * dx

    def calc_energy(self, index, next_node=False):
        node0 = self.nodes[index]
        node1 = node0 if not next_node else self.nodes[index+1]
        for num in xrange(3):
            p = node0[num]
            dist = p.current_dist if not next_node else p.next_dist
            for n, i in enumerate(self.get_index(num)):
                self.bonding_force(p, node1[i], dist[n])

    def calc_bonding_energy(self):
        self._bond_energy = 0
        for index in xrange(self.num - 1):
            self.calc_energy(index)
            self.calc_energy(index, next_node=True)

        self.calc_energy(self.num-1)
        return self._bond_energy

    """ MD Step """

    def update_forces(self):
        for num, p in enumerate(self.particles):
            f = coeff1_3 * p.f
            for node_particle in self.nodes[num]:
                node_particle.f = f

    @staticmethod
    def get_coor_from_node(node):
        return coeff1_3 * sum([p.r for p in node])

    def update_coordinates(self):
        for num, node in enumerate(self.nodes):
            self.particles[num].r = self.get_coor_from_node(node)

    def step(self, h, total_max_step):
        self.update_forces()
        max_step = 0
        for node in self.nodes:
            dr = np.array([0., 0., 0.])
            for p in node:
                dr += h * p.v + .5 * h * h * self._m * p.f
                dr2 = dr.dot(dr)
                if dr2 > max_step:
                    max_step = dr2
                    p.r += dr
                    p.v += h * self._m * p.f
        max_step = sqrt(max_step)
        self.update_coordinates()
        return max_step if max_step > total_max_step else total_max_step

    """ Magic Methods """

    def __iter__(self):
        for p in self.particles:
            yield p

    def __getitem__(self, index):
        return self.particles[index]

    def __repr__(self):
        return "<Nanotube {0}>".format(self.nan_id)

