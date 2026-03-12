from pydantic import BaseModel, Field


class ProbeConfig(BaseModel):
    """Pydantic model to strictly hold and validate our required configurations."""
    project_code: str = Field(alias="project_code")
    server_command: str
    transport: str
    service_url: str
    generate_new: bool = False

    model_config = {"populate_by_name": True}

    @property
    def server_id(self) -> str:
        """Backward-compatible alias for project_code."""
        return self.project_code
