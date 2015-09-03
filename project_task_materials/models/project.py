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


class ProjectTaskType(models.Model):
    _inherit = 'project.task.type'

    consume_material = fields.Boolean(
        string='Consume Material',
        help="""If check this option, when a task change at this state
        consume associated materials""")


class Task(models.Model):
    _inherit = "project.task"

    def _get_stock_move(self):
        move_ids = [line.stock_move_id.id for line in self.material_ids]
        self.stock_move_ids = self.env['stock.move'].browse(move_ids)

    def _get_analytic_line(self):
        line_ids = [line.analytic_line_id.id for line in self.material_ids]
        self.analytic_line_ids = \
            self.env['account.analytic.line'].browse(line_ids)

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
    consume_material = fields.Boolean(related='stage_id.consume_material')
    stock_move_ids = fields.One2many(
        comodel_name='stock.move', compute='_get_stock_move',
        string='Stock Moves')
    stock_state = fields.Selection(
        [('pending', 'Pending'),
         ('confirmed', 'Confirmed'),
         ('assigned', 'Assigned'),
         ('done', 'Done')], compute='_check_stock_state', string='Stock State')
    analytic_line_ids = fields.One2many(
        comodel_name='account.analytic.line', compute='_get_analytic_line',
        string='Analytic Lines')

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
            if self.consume_material:
                self.material_ids.create_stock_move()
                self.material_ids.create_analytic_line()
            else:
                self.unlink_stock_move()
                self.analytic_line_ids.unlink()
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
    analytic_line_id = fields.Many2one(
        comodel_name='account.analytic.line', string='Analytic Line')

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

    def _prepare_analityc_line(self):
        product = self.product_id
        company_id = self.env['res.company']._company_default_get(
            'account.analytic.line')
        journal = self.env.ref(
            'project_task_materials.analytic_journal_sale_materials')
        res = {
            'name': self.task_id.name + ': ' + product.name,
            'ref': self.task_id.name,
            'product_id': product.id,
            'journal_id': journal.id,
            'unit_amount': self.quantity,
            'account_id': self.task_id.project_id.analytic_account_id.id,
            'to_invoice':
                self.task_id.project_id.analytic_account_id.to_invoice.id,
            'user_id': self._uid,
        }
        analytic_line_obj = self.pool.get('account.analytic.line')
        amount_dic = analytic_line_obj.on_change_unit_amount(
            self._cr, self._uid, self._ids, product.id, self.quantity,
            company_id, False, journal.id, self._context)
        res.update(amount_dic['value'])
        return res

    @api.one
    def create_analytic_line(self):
        move_id = self.env['account.analytic.line'].create(
            self._prepare_analityc_line())
        self.analytic_line_id = move_id.id


