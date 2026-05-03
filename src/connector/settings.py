from datetime import timedelta
from connectors_sdk import (
    BaseConfigModel,
    BaseConnectorSettings,
    BaseExternalImportConnectorConfig,
    ListFromString
)
from pydantic import Field


class ExternalImportConnectorConfig(BaseExternalImportConnectorConfig):
    #This field is for the ID of the Connector, the same in the .env file
    id: str = Field(
        description="A UUID v4 to identify the connector in OpenCTI.",
        default="2280522b-4f5f-48c9-a7a9-bf9c99a8ed72",
    )
    #This field is for the scope of the Connector, as in the .enf file
    scope: ListFromString = Field(
        description="The scope of the connector. Only these object types will be imported on OpenCTI.",
        default=[
            "identity",
            "report"
        ],
    )
    #This field is for the name of the connector
    name: str = Field(
        description="Name of the connector.",
        default="[C] AI Incident Database Connector",
    )
    #This field is for the delta time between to runs of the connector
    duration_period: timedelta = Field(
        description="Interval between two runs",
        default=timedelta(days=7),
    )


class AIIDConfig(BaseConfigModel):
    #This field is for the GraphQL API to query the database
    graphql_url: str = Field(
        description="AIID GraphQL API endpoint.",
        default="https://incidentdatabase.ai/api/graphql",
    )
    #This field is to set the batch size for the API call
    batch_size: int = Field(
        description="Number of incidents per API call.",
        default=75,
    )
    #This field is to set the time between two API call
    batch_delay: int = Field(
        description="Delay in seconds between batches.",
        default=1,
    )
    #This field is to set the starting date to query the database
    start_date: str = Field(
        description="Import incidents from this date (ISO 8601). Empty = all history.",
        default="",
    )
    confidence_level: int = Field(
        description="Confidence level for imported objects (0-100).",
        default=75,
    )
    #This field is for the author of the KB
    author_name: str = Field(
        description="Name of the identity that will own imported objects.",
        default="AI Incident Database",
    )
    #This field is for the type of the author
    author_identity_class: str = Field(
        description="STIX identity class for the author.",
        default="organization",
    )


class ConnectorSettings(BaseConnectorSettings):
    connector: ExternalImportConnectorConfig = Field(
        default_factory=ExternalImportConnectorConfig
    )
    aiid: AIIDConfig = Field(
        default_factory=AIIDConfig
    )