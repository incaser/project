# -*- coding: utf-8 -*-
##############################################################################
#
#    Copyright (C) 2012 - 2013 Daniel Reis
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License as
#    published by the Free Software Foundation, either version 3 of the
#    License, or (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Affero General Public License for more details.
#
#    You should have received a copy of the GNU Affero General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
##############################################################################

from openerp import models, fields, api
from openerp.tools.float_utils import float_round


class Task(models.Model):
    _inherit = "project.task"

    def _get_stock_move(self):
        move_ids = [line.stock_move_id.id for line in self.material_ids]
        self.stock_move_ids = self.env['stock.move'].browse(move_ids)

    def _check_stock_state(self):
        if not self.stock_move_ids:
            self.stock_state = 'pending'
        elif self.stock_move_ids.filtered(lambda r: r.state == 'confirmed'):
            self.stock_state = 'confirmed'
        elif self.stock_move_ids.filtered(lambda r: r.state == 'assigned'):
            self.stock_state = 'assigned'
        elif self.stock_move_ids.filtered(lambda r: r.state == 'done'):
            self.stock_state = 'done'

    material_ids = fields.One2many(
        comodel_name='project.task.materials', inverse_name='task_id',
        string='Materials used')
    stage_closed = fields.Boolean(related='stage_id.closed')
    stock_move_ids = fields.One2many(
        comodel_name='stock.move', compute='_get_stock_move',
        string='Stock Moves')
    stock_state = fields.Selection(
        [('confirmed', 'Confirmed'),
         ('assigned', 'Assigned'),
         ('done', 'Done')], compute='_check_stock_state', string='Stock State')

    @api.one
    def unlink_stock_move(self):
        for move in self.stock_move_ids:
            if move.state == 'assigned':
                move.do_unreserve()
            if move.state in ['waiting', 'confirmed', 'assigned']:
                move.state = 'draft'
            move.unlink()

    @api.one
    def write(self, vals):
        res = super(Task, self).write(vals)
        if 'stage_id' in vals:
            if self.stage_closed:
                self.material_ids.create_stock_move()
            else:
                self.unlink_stock_move()
        return res

    @api.multi
    def action_assign(self):
        self.stock_move_ids.action_assign()

    @api.multi
    def action_done(self):
        self.stock_move_ids.action_done()


class ProjectTaskMaterials(models.Model):
    _name = "project.task.materials"
    _description = "Task Materials Used"
    task_id = fields.Many2one(
        comodel_name='project.task', string='Task', ondelete='cascade',
        required=True)
    product_id = fields.Many2one(
        comodel_name='product.product', string='Product', required=True)
    quantity = fields.Float(string='Quantity')
    stock_move_id = fields.Many2one(
        comodel_name='stock.move', string='Stock Move')

    def _prepare_stock_move(self):
        product = self.product_id
        res = {
            'product_id': product.id,
            'name': product.partner_ref,
            'state': 'confirmed',
            'product_uom': product.uom_id.id,
            'product_uos':
                product.uos_id and product.uos_id.id or False,
            'product_uom_qty': self.quantity,
            'product_uos_qty': self.quantity,
            'origin': self.task_id.name,
            'location_id':
                product.product_tmpl_id.property_stock_procurement.id,
            'location_dest_id': self.env.ref(
                'stock.stock_location_customers').id,
        }
        if product.uos_id and product.uom_id and \
                (product.uos_id != product.uom_id):
            precision = self.env['decimal.precision'].precision_get(
                'Product UoS')
            res['product_uos_qty'] = float_round(
                self.quantity * product.uos_coeff, precision_digits=precision)
        return res

    @api.one
    def create_stock_move(self):
        move_id = self.env['stock.move'].create(self._prepare_stock_move())
        self.stock_move_id = move_id.id
