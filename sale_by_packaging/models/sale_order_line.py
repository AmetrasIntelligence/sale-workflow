# Copyright 2020 Camptocamp SA
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl)
from odoo import _, api, models
from odoo.exceptions import ValidationError
from odoo.tools import float_compare, float_repr, float_round


class SaleOrderLine(models.Model):

    _inherit = "sale.order.line"

    def _can_be_sold_error_condition(self):
        self.ensure_one()
        return self.product_packaging and not self.product_packaging.can_be_sold

    @api.constrains("product_packaging")
    def _check_product_packaging_can_be_sold(self):
        for line in self:
            if line._can_be_sold_error_condition():
                raise ValidationError(
                    _(
                        "Packaging %s on product %s must be set as 'Can be sold'"
                        " in order to be used on a sale order."
                    )
                    % (line.product_packaging.name, line.product_id.name)
                )

    @api.onchange("product_packaging")
    def _onchange_product_packaging(self):
        if self._can_be_sold_error_condition():
            return {
                "warning": {
                    "title": _("Warning"),
                    "message": _(
                        "This product packaging must be set as 'Can be sold' in"
                        " order to be used on a sale order."
                    ),
                },
            }
        return super()._onchange_product_packaging()

    @api.constrains(
        "product_id", "product_packaging", "product_packaging_qty", "product_uom_qty"
    )
    def _check_product_packaging_sell_only_by_packaging(self):
        for line in self:
            if not line.product_id.sell_only_by_packaging:
                continue
            if (
                not line.product_packaging
                or float_compare(
                    line.product_packaging_qty,
                    0,
                    precision_rounding=line.product_id.uom_id.rounding,
                )
                <= 0
            ):
                raise ValidationError(
                    _(
                        "Product %s can only be sold with a packaging and a "
                        "packaging qantity." % line.product_id.name
                    )
                )

    def get_packaging_qty(self, vals=None):
        if not vals:
            vals = []
        product = (
            self.env["product.product"].browse(vals["product_id"])
            if "product_id" in vals
            else self.product_id
        )

        quantity = (
            vals["product_uom_qty"]
            if "product_uom_qty" in vals
            else self.product_uom_qty
        )
        uom = (
            self.env["uom.uom"].browse(vals["product_uom"])
            if "product_uom" in vals
            else self.product_uom
        )
        packaging = (
            self.env["product.packaging"].browse(vals["product_packaging"])
            if "product_packaging" in vals
            else self.product_packaging
        )

        return product._convert_packaging_qty(
            quantity, uom or product.uom_id, packaging=packaging,
        )

    def _force_qty_with_package(self):
        """

        :return:
        """
        self.ensure_one()
        self.product_uom_qty = self.get_packaging_qty()
        return True

    @api.onchange("product_uom_qty", "product_id")
    def _onchange_product_uom_qty(self):
        self._force_packaging()
        self._force_qty_with_package()
        res = super()._onchange_product_uom_qty()
        return res

    def _get_product_packaging_having_multiple_qty(self, product, qty, uom):
        if uom != product.uom_id:
            qty = uom._compute_quantity(qty, product.uom_id)
        return product.get_first_packaging_with_multiple_qty(qty)

    def _inverse_product_packaging_qty(self):
        # Force skipping of auto assign
        # if we are writing the product_uom_qty directly via inverse
        super(
            SaleOrderLine, self.with_context(_skip_auto_assign=True)
        )._inverse_product_packaging_qty()

    def _inverse_qty_delivered(self):
        # Force skipping of auto assign
        super(
            SaleOrderLine, self.with_context(_skip_auto_assign=True)
        )._inverse_qty_delivered()

    def write(self, vals):
        """Auto assign packaging if needed"""
        if vals.get("product_packaging") or self.env.context.get("_skip_auto_assign"):
            # setting the packaging directly, skip auto assign
            return super().write(vals)
        for line in self:
            line_vals = vals.copy()
            if line_vals.get("product_id", False):
                packaging = line._get_autoassigned_packaging(line_vals)
                if packaging:
                    line_vals.update({"product_packaging": packaging})
            if line_vals.get("product_uom_qty") or line_vals.get("product_id"):
                product_qty = line.get_packaging_qty(line_vals)
                line_vals.update({"product_uom_qty": product_qty})
            super(SaleOrderLine, line).write(line_vals)
        return True

    @api.model
    def create(self, vals):
        """Auto assign packaging if needed"""
        # Fill the packaging if they are empty and the quantity is a multiple
        if not vals.get("product_packaging"):
            packaging = self._get_autoassigned_packaging(vals)
            if packaging:
                vals.update({"product_packaging": packaging})
        if vals.get("product_uom_qty") or vals.get("product_id"):
            product_qty = self.get_packaging_qty(vals)
            vals.update({"product_uom_qty": product_qty})
        return super().create(vals)

    def _get_autoassigned_packaging(self, vals=None):
        if not vals:
            vals = []
        product = (
            self.env["product.product"].browse(vals["product_id"])
            if "product_id" in vals
            else self.product_id
        )
        if product and product.sell_only_by_packaging:
            quantity = (
                vals["product_uom_qty"]
                if "product_uom_qty" in vals
                else self.product_uom_qty
            )
            uom = (
                self.env["uom.uom"].browse(vals["product_uom"])
                if "product_uom" in vals
                else self.product_uom
            )
            packaging = self._get_product_packaging_having_multiple_qty(
                product, quantity, uom
            )
            if packaging:
                return packaging.id
        return None

    def _force_packaging(self):
        if not self.product_packaging and self.product_id.sell_only_by_packaging:
            packaging_id = self._get_autoassigned_packaging()
            if packaging_id:
                self.product_packaging = packaging_id

    def _check_package(self):
        if self.product_packaging:
            product_precision = self.env["decimal.precision"].precision_get(
                "Product Unit of Measure"
            )
            package_precision = self.product_packaging.sale_rounding
            if self.product_packaging and self.product_packaging.qty:
                pkg_qty = self.product_uom_qty / self.product_packaging.qty
            else:
                pkg_qty = 0.00
            multiplier = pkg_qty // self.product_packaging.sale_rounding
            rest = pkg_qty % self.product_packaging.sale_rounding
            product_packaging_qty = float_round(
                (multiplier + (1 if rest else 0))
                * self.product_packaging.sale_rounding,
                precision_digits=product_precision,
            )
            product_uom_qty = product_packaging_qty * self.product_packaging.qty
            if (
                float_compare(
                    self.product_packaging_qty,
                    product_packaging_qty,
                    precision_digits=product_precision,
                )
                != 0
                or float_compare(
                    self.product_uom_qty,
                    product_uom_qty,
                    precision_digits=product_precision,
                )
                != 0
            ):
                self.product_packaging_qty = product_packaging_qty
                self.product_uom_qty = product_uom_qty
                return {
                    "warning": {
                        "title": _("Warning"),
                        "message": _(
                            "Increased quantity to %s %s since package '%s' "
                            "contains %s %s and can only be splitted "
                            "into %s pieces."
                        )
                        % (
                            float_repr(
                                self.product_uom_qty, precision_digits=product_precision
                            ),
                            self.product_id.uom_id.name,
                            self.product_packaging.name,
                            float_repr(
                                self.product_packaging.qty,
                                precision_digits=product_precision,
                            ),
                            self.product_id.uom_id.name,
                            round(1 / package_precision, 0),
                        ),
                    },
                }
            return {}
