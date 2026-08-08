from odoo import fields, models


class TestDashboard(models.Model):
    _name = 'test_module.dashboard'
    _description = 'Test Dashboard'

    name = fields.Char(required=True)
