# -*- coding: utf-8 -*-
# See README.rst file on addon root folder for license details

{
    'name': 'Project Task Materials',
    'summary': 'Record products spent in a Task',
    'version': '1.0',
    'category': "Project Management",
    'author': "Odoo Community Association (OCA)",
    'license': 'AGPL-3',
    'description': "",
    'depends': ['project', 'stock', 'account', 'analytic', 'sale_service'],
    'data': [
        'data/project_task_materials_data.xml',
        'views/project_view.xml',
        'security/ir.model.access.csv',
    ],
    'installable': True,
}
