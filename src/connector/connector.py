import uuid
from datetime import datetime, timezone
from typing import Optional

import stix2
from stix2 import (
    Identity,
    Incident,
    Relationship,
    Report,
    Bundle,
    ExternalReference,
)
from pycti import OpenCTIConnectorHelper
from connector.settings import ConnectorSettings
from aiid_client import AIIDClient


def _patched_initiate_work(
    self, connector_id: str, friendly_name: str, is_multipart: bool = False
) -> Optional[str]:


    """
    This function query the database without the 'is_multipart'. 
    If you are using a version of OpenCTI <= 7.260428.0 use this method, otherwise comment it.

    :param connector_id: the connector id
    :param friendly_name: the friendly name for the work
    :param is_multipart: indicates whether multiple calls to `add_expectations`
                                are to be expected during the lifetime of the work.
                                In consequence the work won't automatically
                                transition to `complete` when the number of calls
                                to `report_expectation` matches the expectations
                                but only when an explicit call to `to_processed`
                                is made.
                                Should be set to `True` when sending multiple
                                STIX bundles consecutively via `send_stix2_bundle`
    :return: the id of the work added
    """

    query = """
        mutation WorkAdd($connectorId: String!, $friendlyName: String!) {
            workAdd(connectorId: $connectorId, friendlyName: $friendlyName) {
                id
            }
        }
    """
    work = self.api.query(query, {
        "connectorId": connector_id,
        "friendlyName": friendly_name,
    })
    return work["data"]["workAdd"]["id"]


class AIIDConnector:
    def __init__(self, config: ConnectorSettings, helper: OpenCTIConnectorHelper):
        self.config = config
        self.helper = helper
        self.client = AIIDClient(
            graphql_url=config.aiid.graphql_url,
            batch_size=config.aiid.batch_size,
            batch_delay=config.aiid.batch_delay,
        )

        """
        The following code is useful to mutate the patched initiate work
        If you are using a version of OpenCTI <= 7.260428.0 use this method, otherwise comment it.
        """

        import types
        self.helper.api.work.initiate_work = types.MethodType(
            _patched_initiate_work, self.helper.api.work
        )

    def _parse_date(self, date_str: str) -> Optional[datetime]:
        """
        This function safely parse a date string to datetime. Returns None if empty.
        
        :param date_str: the string date
        :return: the datetime, otherwise None
        """
        if not date_str:
            return None
        try:
            if "T" in date_str:
                return datetime.fromisoformat(date_str.replace("Z", "+00:00"))
            return datetime.strptime(date_str, "%Y-%m-%d").replace(
                tzinfo=timezone.utc
            )
        except Exception:
            return None

    def _incident_to_stix_bundle(self, incident: dict) -> Bundle:
        """
        This function transform a single incident into a STIX Bundle. 

        Workflow:
        For each incident:
            1) Create author Identity (AI Incident Database)
            2) Create Incident entity linking to author
            3) Extract Deployers and link them to the Incident
            4) For each report related to the incident:
               - If report already exists in OpenCTI → link incident to report
               - If report does not exist → create report and link to incident
        
        :param incident: the dictionary of the incident
        :return: a Bundle object for this incident
        """
        stix_objects = []
        # 1) AUTHOR — Identity representing AI Incident Database
        author_name = "AI Incident Database"
        author_stix_id = f"identity--{uuid.uuid5(uuid.NAMESPACE_URL, author_name)}"

        ext_ref_author = ExternalReference(
            source_name="AI Incident Database",
            url="https://incidentdatabase.ai/",
            description=incident.get("title", ""),
        )

        stix_author = Identity(
            id=author_stix_id,
            name=author_name,
            identity_class="organization",
            description="Official database for AI incidents. Connector identity for AI Incident Database data. All objects imported by this connector are owned by this identity.",
            confidence=75,
            contact_information="https://incidentdatabase.ai/",
            external_references=[ext_ref_author],
            allow_custom=True,
        )
        stix_objects.append(stix_author)

        # 2) INCIDENT — Core entity

        incident_stix_id = (
            f"incident--{uuid.uuid5(uuid.NAMESPACE_URL, str(incident.get('incident_id')))}"
        )

        ext_ref_incident = ExternalReference(
            source_name="AI Incident Database",
            url=f"https://incidentdatabase.ai/cite/{incident.get('incident_id')}/",
            description=incident.get("title", ""),
        )

        # Build labels from classifications if available
        labels = [
            f"Risk: {e.get('namespace')}"
            for e in incident.get("classifications", [])
            if e.get("namespace")
        ]
        # Fallback label if no classifications
        if not labels:
            labels = ["ai-incident"]

        stix_incident = Incident(
            #last_seen=self._parse_date(incident.get("date_modified")) or datetime.now(timezone.utc),
            id=incident_stix_id,
            name=f"AIID-{incident.get('incident_id')}: {incident.get('title')}",
            description=incident.get("description", "No description."),
            created = min(self._parse_date(incident.get("date_modified")) or datetime.now(timezone.utc), self._parse_date(incident.get("created_at")) or datetime.now(timezone.utc)),
            modified = max(self._parse_date(incident.get("date_modified")) or datetime.now(timezone.utc), self._parse_date(incident.get("created_at")) or datetime.now(timezone.utc)),
            first_seen = min(self._parse_date(incident.get("date_modified")) or datetime.now(timezone.utc), self._parse_date(incident.get("created_at")) or datetime.now(timezone.utc)),
            last_seen = max(self._parse_date(incident.get("date_modified")) or datetime.now(timezone.utc), self._parse_date(incident.get("created_at")) or datetime.now(timezone.utc)),
            labels=labels,
            confidence=100,
            source="AI Incident Database",
            created_by_ref=author_stix_id,
            external_references=[ext_ref_incident],
            allow_custom=True,
        )
        stix_objects.append(stix_incident)

        # 3) DEPLOYERS — Identity + Relationship to Incident

        for dep in incident.get("AllegedDeployerOfAISystem", []):
            if not dep.get("name"):
                continue

            deployer_id = (
                f"identity--{uuid.uuid5(uuid.NAMESPACE_URL, str(dep.get('entity_id', dep.get('name'))))}"
            )

            stix_deployer = Identity(
                id=deployer_id,
                name=dep.get("name"),
                identity_class="organization",
                confidence=100,
            )

            stix_rel = Relationship(
                id=f"relationship--{uuid.uuid5(uuid.NAMESPACE_URL, f'{stix_incident.id}+related-to+{stix_deployer.id}')}",
                relationship_type="related-to",
                source_ref=stix_incident.id,
                target_ref=stix_deployer.id,
            )

            stix_objects.extend([stix_deployer, stix_rel])

        # 4) REPORTS — Create or link to existing
        # OpenCTI handles deduplication automatically via deterministic ID:
        # - Report NOT EXISTS → creates it and links to Incident
        # - Report EXISTS → keeps existing data, ADDS Incident to links
        for rep in incident.get("reports", []):
            unique_report_key = str(rep.get("report_number") or rep.get("url", ""))
            if not unique_report_key:
                continue

            report_stix_id = f"report--{uuid.uuid5(uuid.NAMESPACE_URL, unique_report_key)}"

            ext_ref_report = ExternalReference(
                source_name=rep.get("source_domain", "AI Incident Database"),
                url=rep.get("url", ""),
                description=rep.get("description", ""),
            )

            best_title = (
                rep.get("title")
                or rep.get("source_domain")
                or "Unknown"
            )

            report_labels = [
                f"Submitter: {s}"
                for s in rep.get("submitters", [])
                if s
            ]
            if rep.get("language"):
                report_labels.append(f"Language: {rep.get('language')}")

            stix_report = Report(
                id=report_stix_id,
                name=f"Report AIID - {best_title}",
                report_types=["threat-report"],
                description=rep.get("description", ""),
                revoked=False,
                external_references=[ext_ref_report],
                object_refs=[stix_incident.id],
                published=self._parse_date(rep.get("date_published")) or datetime.now(timezone.utc),
                created=self._parse_date(rep.get("created_at")) or datetime.now(timezone.utc),
                modified=self._parse_date(rep.get("date_submitted")) or datetime.now(timezone.utc),
                confidence=100,
                labels=report_labels if report_labels else ["ai-incident-report"],
                created_by_ref=author_stix_id,
                allow_custom=True,
            )
            stix_objects.append(stix_report)

        return Bundle(objects=stix_objects, allow_custom=True)

    def _run_once(self):
        """
        This function si useful to: 
            1) Download of all the incident from AI Incident Database
            2) Convert the single incident into STIX Bundle to OpenCTI (updating the work status),
            3) Update the info related to import (i.e., "last_run")
        """
        work_id = None
        self.helper.log_info("Starting import from AI Incident Database...")
        try:
            work_id = self.helper.api.work.initiate_work(
                self.helper.connect_id,
                "AI Incident Database — importing incidents"
            )
            self.helper.log_info(f"Work initiated with ID: {work_id}")

            incidents = self.client.get_all_incidents()
            total = len(incidents)
            self.helper.log_info(f"Fetched {total} incidents from AIID.")

            for i, incident in enumerate(incidents):
                bundle = self._incident_to_stix_bundle(incident)
                self.helper.send_stix2_bundle(
                    bundle.serialize(),
                    work_id=work_id,
                    cleanup_inconsistent_bundle=True,
                )
                if i % 50 == 0:
                    self.helper.log_info(
                        f"Progress: {i}/{total} incidents processed."
                    )

            self.helper.set_state({
                "last_run": datetime.now(timezone.utc).isoformat(),
                "last_count": total,
            })

            self.helper.api.work.to_processed(
                work_id,
                f"AI Incident Database: successfully imported {total} incidents."
            )
            self.helper.log_info(
                f"Import completed successfully: {total} incidents processed."
            )

        except Exception as e:
            self.helper.log_error(
                f"An unexpected error occurred during import: {e}"
            )
            if work_id:
                self.helper.api.work.to_processed(
                    work_id,
                    f"Import failed with error: {str(e)}",
                    in_error=True,
                )
            raise

    def run(self):
        """
        This function run the connector's features
        """
        
        self.helper.log_info("Starting the AI Incident Database connector.")
        self.helper.schedule_iso(
            message_callback=self._run_once,
            duration_period=str(self.config.connector.duration_period),
        )