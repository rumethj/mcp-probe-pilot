from pydantic import BaseModel, Field


class ProbeConfig(BaseModel):
    """Pydantic model to strictly hold and validate our required configurations."""
    project_code: str = Field(alias="project_code")
    server_command: str
    transport: str
    service_url: str
    generate_new: bool = False
    features_dir: str | None = Field(
        default=None,
        description="Relative path override for the features output directory. "
                    "Defaults to 'features' under the repository root when not set.",
    )
    test_env: dict[str, str] = Field(
        default_factory=dict,
        description="Environment variables injected into the server process "
                    "during test execution and discovery.",
    )

    model_config = {"populate_by_name": True}

    @property
    def server_id(self) -> str:
        """Backward-compatible alias for project_code."""
        return self.project_code
