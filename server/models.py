from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import relationship
from uuid import uuid4

db = SQLAlchemy()

class User(db.Model):
    __tablename__ = "users"
    id = db.Column(db.String, primary_key=True, default=uuid4) 
    email = db.Column(db.String, unique=True)
    password = db.Column(db.String(255))
    containers = relationship("Container", backref="user", lazy=True)

class Container(db.Model):
    id = db.Column(db.String(64), primary_key=True)
    name = db.Column(db.String(512))
    status = db.Column(db.String(512))
    user_id = db.Column(db.String, db.ForeignKey('users.id'), nullable=False)