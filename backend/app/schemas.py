from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

# Keys follow the usual env-var convention: letters, digits, underscore; not starting with a digit.
KEY_PATTERN = r"^[A-Za-z_][A-Za-z0-9_]*$"


class EnvironmentBase(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    description: str | None = None


class EnvironmentCreate(EnvironmentBase):
    pass


class EnvironmentUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = None


class EnvironmentRead(EnvironmentBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    variable_count: int = 0
    created_at: datetime
    updated_at: datetime


class VariableBase(BaseModel):
    key: str = Field(min_length=1, max_length=255, pattern=KEY_PATTERN)
    value: str = ""
    is_secret: bool = False


class VariableCreate(VariableBase):
    pass


class VariableUpdate(BaseModel):
    key: str | None = Field(default=None, min_length=1, max_length=255, pattern=KEY_PATTERN)
    value: str | None = None
    is_secret: bool | None = None


class VariableRead(VariableBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    environment_id: int
    created_at: datetime
    updated_at: datetime
