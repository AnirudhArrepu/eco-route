from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import SecretStr

class Settings(BaseSettings):
    environment: str = "development"
    database_url: str = "sqlite:///./ecoroute.db"
    database_secret_arn: str = ""
    database_host: str = ""
    database_port: int = 5432
    aws_region: str = "ap-south-1"
    aws_integrations_enabled: bool = False
    cognito_user_pool_id: str = ""
    cognito_app_client_id: str = ""
    auth_required: bool = False
    bedrock_model_id: str = ""
    openai_api_key: SecretStr | None = None
    openai_base_url: str = ""
    openai_project_id: str = ""
    step_functions_state_machine_arn: str = ""
    step_functions_enabled: bool = False
    strands_agent_enabled: bool = False
    strands_max_tool_calls: int = 8
    location_index_name: str = ""
    location_route_calculator_name: str = ""
    cors_origins: str = "http://localhost:3000,http://localhost:5173"
    proposal_ttl_minutes: int = 30
    auto_migrate: bool = True
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    @property
    def origins(self):
        return [x.strip() for x in self.cors_origins.split(",") if x.strip()]

    @property
    def mantle_enabled(self):
        return bool(self.openai_api_key and self.openai_api_key.get_secret_value() and self.openai_base_url)

settings = Settings()
