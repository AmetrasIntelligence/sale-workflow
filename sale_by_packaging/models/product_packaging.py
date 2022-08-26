# Copyright 2020 Camptocamp SA
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl)
from odoo import api, fields, models


class ProductPackaging(models.Model):
    _inherit = "product.packaging"

    can_be_sold = fields.Boolean(
        string="Can be sold", compute="_compute_can_be_sold", readonly=False, store=True
    )

    force_sale_qty = fields.Boolean(
        string="Force sale quantity",
        help="Determine if during the creation of a sale order line, the "
        "quantity should be forced with a multiple of the packaging.\n"
        "Example:\n"
        "You sell a product by packaging of 5 products.\n"
        "When the user will put 3 as quantity, the system can force the "
        "quantity to the superior unit (5 for this example).",
    )

    sale_rounding = fields.Float(
        string="Sale Rounding Precision",
        digits="Product Unit of Measure",
        required=True,
        default=0.1,
        help="The allowed package quantity will be a multiple of this value. "
        "Use 1.0 for a package that cannot be further split.",
    )

    actual_sale_qty = fields.Float(compute="_compute_actual_sale_qty")

    @api.depends("sale_rounding", "qty")
    def _compute_actual_sale_qty(self):
        for record in self:
            record.actual_sale_qty = record.sale_rounding * record.qty

    @api.depends("packaging_type_id")
    def _compute_can_be_sold(self):
        for record in self:
            record.can_be_sold = record.packaging_type_id.can_be_sold
