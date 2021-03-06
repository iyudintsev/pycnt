import numpy as np
from nanotubes import Nanotubes
from vanderwaals import calc_vanderwaals_energy, calc_vanderwaals_forces
from coul import ChargeCalc, calc_coul_energy, calc_coul_forces, check_coul_condition
from config import h_max, h_coul, time_of_calc, dump_file
from config import fire_alpha0, fire_n_min, fire_f_alpha, fire_f_dec, fire_f_inc, max_step_lim


class Model(object):
    def __init__(self, num, coordinates):
        """
        Constructor
        :param num: int, number of particles in one nanotube
        """
        self.nanotubes = Nanotubes(num)
        self.nanotubes.set_coordinates(coordinates)

        check_coul_condition()
        self.charge_calc = ChargeCalc(self.nanotubes)
        self.h = h_max  # current step
        self.t = 0  # current time
        self.t_coul = 0  # control process charge calc
        self.t_repr = 0  # control of repr
        self.repr_now = False
        self.step_counter = 0
        """ Dump Coordinates """
        self.dump_file = None
        self.init_dump_file()

        """ FIRE """
        self.fire_counter = 0
        self.fire_alpha = fire_alpha0

        """ Energy """
        self.bonding_energy = 0
        self.vanderwaals_energy = 0
        self.coul_energy = 0

    def init_dump_file(self):
        with open(dump_file, "w") as f:
            f.write('')
        self.dump_file = open(dump_file, "a")

    @property
    def total_energy(self):
        return self.bonding_energy + self.vanderwaals_energy + self.coul_energy

    def print_energy(self):
        print "time {0}".format(self.t)
        print '\tbonding energy:', self.bonding_energy / 1.6e-12
        print '\tcoul energy:', self.coul_energy / 1.6e-12
        print '\ttotal energy:', self.total_energy / 1.6e-12

    """ Energy Calculation """

    def calc_bonding_energy(self):
        self.bonding_energy = 0
        for nanotube in self.nanotubes:
            self.bonding_energy += nanotube.calc_bonding_energy()

    def calc_vanderwaals_energy(self):
        self.vanderwaals_energy = 0
        for nanotube_i in self.nanotubes:
            for p_i in nanotube_i:
                for nanotube_j in self.nanotubes:
                    if nanotube_i == nanotube_j:
                        continue
                    for p_j in nanotube_j:
                        self.vanderwaals_energy += calc_vanderwaals_energy(p_i, p_j)  # TODO fix duplication problem
        self.vanderwaals_energy *= .5

    def calc_coul_energy(self):
        self.coul_energy = calc_coul_energy(self.nanotubes)
        return self.coul_energy

    def calc_energy(self):
        self.calc_bonding_energy()
        self.calc_coul_energy()

    """ Forces Calculation"""
    
    def calc_bonding_forces(self):
        for nanotube in self.nanotubes:
            nanotube.calc_bonding_forces()

    def calc_vanderwaals_forces(self):
        for nanotube_i in self.nanotubes:
            for p_i in nanotube_i:
                for nanotube_j in self.nanotubes:
                    if nanotube_i == nanotube_j:
                        continue
                    for p_j in nanotube_j:
                        calc_vanderwaals_forces(p_i, p_j)  # TODO fix duplication problem

    def calc_coul_forces(self):
        calc_coul_forces(self.nanotubes)

    """ FIRE algorithm """

    def fire_algorithm(self, max_step):
        fire_p = 0
        f_norm = 0
        v_norm = 0

        for p in self.nanotubes.get_node_particles():
            #print([p.v, p.f])
            fire_p += p.f.dot(p.v)
            f_norm += p.f.dot(p.f)
            v_norm += p.v.dot(p.v)
        f_norm = np.sqrt(f_norm)
        _f_norm = 1. / f_norm
        v_norm = np.sqrt(v_norm)

        #print("Fire P ",fire_p)
        for p in self.nanotubes.get_node_particles():
            f_n = p.f * _f_norm
            p.v = (1 - self.fire_alpha) * p.v + self.fire_alpha * v_norm * f_n

        if fire_p > 0 and self.fire_counter > fire_n_min:
            self.fire_counter = 0
            h_f_inc = self.h * fire_f_inc
            self.h = h_f_inc if h_f_inc < h_max else h_max
            self.fire_alpha *= fire_f_alpha
        elif fire_p < 0:
            self.h *= fire_f_dec
            for p in self.nanotubes.get_node_particles():
                p.v = np.array([0., 0., 0.])
            self.fire_alpha = fire_alpha0
        else:
            self.fire_counter += 1

        if max_step > max_step_lim:
            self.h *= fire_f_dec

    """ Process of Calculation """

    def dump(self):
        # for nan in self.nanotubes:
        #     for p in nan.get:
        #         out = "{0} {1} {2}\n".format(*p.r)
        #         self.dump_file.write(out)
        for p in self.nanotubes.get_node_particles():
            out = "{0} {1} {2}\n".format(*p.r)
            self.dump_file.write(out)

    def calc(self):
        self.dump()
        self.charge_calc.run()
        print "\t charges calculated"

        self.calc_coul_forces()
        print "\t coul forces calculated"

        # self.calc_vanderwaals_forces()
        # print "\t vanderwaals forces calculated"
        self.step_counter += 1
        self.calc_energy()
        self.print_energy()

        while self.t < time_of_calc:
            max_step = 0
            for nan in self.nanotubes:
                max_step = nan.step(self.h, max_step)

            if self.step_counter % 200 == 0:
                self.calc_energy()
                self.print_energy()
                print "\tmax step:", max_step
                print "\th:", self.h
                self.dump()
                #self.comp_coul_dir(10)

            if self.t_coul >= h_coul:
                self.t_coul -= h_coul
                self.charge_calc.run()
            self.t_coul += self.h

            self.calc_bonding_forces()
            #if self.step_counter % 200 == 0:
            #    self.nanotubes[0].comp_bonding_dir()

            self.calc_coul_forces()
            # self.calc_vanderwaals_forces()

            self.t += self.h
            self.step_counter += 1
            
            for nan in self.nanotubes:
                nan.update_external_forces()
                
            self.fire_algorithm(max_step)
        self.dump()

    """ Tests """

    def comp_coul_dir(self, num):
        dx = 1e-13
        nan = self.nanotubes[0]
        c = 0
        print '-' * 100
        print "Coul Forces"
        print ''
        for p in nan:
            if c == num:
                break
            f = np.zeros(shape=3)
            for i in xrange(3):
                e0 = self.calc_coul_energy()
                p.r[i] += dx
                e1 = self.calc_coul_energy()
                p.r[i] -= dx
                f[i] = (e0 - e1) / dx
            print f
            print p.f_coul
            print ''
            c += 1
        print '-' * 100

    """ Magic Methods"""

    def __repr__(self):
        counter = self.nanotubes.counter
        num = self.nanotubes.num
        return "<Model: {0} nanotubes, {1} particles>".format(counter, counter * num)

    def __del__(self):
        self.dump_file.close()
