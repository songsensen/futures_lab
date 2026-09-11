from sqlalchemy import inspect
from app.models import SupplyChainNode, VarietyFactor

print("VarietyFactor:", list(inspect(VarietyFactor).relationships.keys()))
print("SupplyChainNode:", list(inspect(SupplyChainNode).relationships.keys()))