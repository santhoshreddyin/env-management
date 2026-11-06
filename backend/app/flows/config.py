"""Configuration-driven styling: protocol colours, line styles and layer ordering."""

import json
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

from app.config import settings

DEFAULT_PATH = Path(__file__).with_name("flow_config.json")


class LayerConfig(BaseModel):
    id: str
    label: str


class ProtocolStyle(BaseModel):
    label: str
    color: str
    dash: str | None = None


class DirectionStyle(BaseModel):
    label: str
    stroke_width: float
    marker: Literal["arrow", "arrowclosed"]


class SystemTypeStyle(BaseModel):
    label: str
    color: str


class FlowConfig(BaseModel):
    layers: list[LayerConfig]
    type_layers: dict[str, str]
    protocols: dict[str, ProtocolStyle]
    directions: dict[str, DirectionStyle]
    system_types: dict[str, SystemTypeStyle]

    @property
    def layer_ids(self) -> list[str]:
        return [layer.id for layer in self.layers]

    def layer_for(self, system_type: str, explicit_layer: str | None) -> str:
        if explicit_layer and explicit_layer in self.layer_ids:
            return explicit_layer
        return self.type_layers.get(system_type, self.layer_ids[-1])


@lru_cache
def get_flow_config() -> FlowConfig:
    path = Path(settings.flow_config_path) if settings.flow_config_path else DEFAULT_PATH
    return FlowConfig.model_validate(json.loads(path.read_text()))
