from pydantic import BaseModel

# Configuration models
class ProbeConfig(BaseModel):
    """Pydantic model to strictly hold and validate our required configurations."""
    project_code: str
    server_command: str
    transport: str
    service_url: str
    generate_new: bool = False
