from marshmallow import Schema, fields

class AdminSchema(Schema):
    id = fields.Int()
    name = fields.Str()
    email = fields.Email()
    role = fields.Str()
    status = fields.Str()
    created = fields.DateTime()


admin_schema = AdminSchema()
admins_schema = AdminSchema(many=True)