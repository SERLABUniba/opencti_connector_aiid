import requests
import time

AIID_GRAPHQL_URL = "https://incidentdatabase.ai/api/graphql/"

INCIDENTS_QUERY = """
query($pagination: PaginationType, $sort: IncidentSortType, $languages: [String]!) {
  incidents (pagination: $pagination, sort: $sort){
    incident_id
    title
    description
    editor_notes
    date
    date_modified
    created_at
    reports {
      url
      source_domain
      authors
      created_at
      date_published
      date_submitted
      description
      image_url
      language
      report_number
      submitters
      title
      text
      tags
      is_incident_report
      inputs_outputs
    }
    implicated_systems {
      name
      entity_id
    }
    AllegedDeployerOfAISystem {
      name
      entity_id
      created_at
      date_modified
    }
    AllegedDeveloperOfAISystem {
      name
      entity_id
      created_at
      date_modified
    }
    AllegedHarmedOrNearlyHarmedParties {
      name
      entity_id
      created_at
    }
    editor_dissimilar_incidents
    editor_similar_incidents
    editors {
      first_name
      last_name
      roles
      userId
    }
    nlp_similar_incidents {
      similarity
      incident_id
    }
    translations(languages: $languages) {
      language
      description
      title
      dirty
    }
    classifications {
      namespace
    }
  }
}
"""


class AIIDClient:
    def __init__(self, graphql_url: str, batch_size: int, batch_delay: int):
        self.graphql_url = graphql_url
        self.batch_size = batch_size
        self.batch_delay = batch_delay
        self.session = requests.Session()
        self.session.headers.update({
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0 (compatible; OpenCTI-AIID-Connector/1.0)",
            "Accept": "application/json",
            "Origin": "https://incidentdatabase.ai",
            "Referer": "https://incidentdatabase.ai/",
        })

    def get_incidents(self, limit: int = 100, skip: int = 0) -> list:
      """
      This function query the database (considering the limit and the skipped incident) and get all the incident

      :param limit: the limit of this query 
      :param skip: the skipped incidents to ignore
      :return: the list of incident obtained
      """
      resp = self.session.post(
          AIID_GRAPHQL_URL,
          json={"query": INCIDENTS_QUERY, "variables": {"pagination": {"limit": limit, "skip": skip}, "sort": {"incident_id":"ASC"}, "languages":["eng"]}},
          timeout=600,
          verify=False
      )
      resp.raise_for_status()
      data = resp.json()
      return data.get("data", {}).get("incidents", [])

    def get_all_incidents(self) -> list:
        """
        This function fetchs all incidents using a pagination (through the skip parameter and batch)
        :return: the list of all incident (for each batch)
        """
        all_incidents = []
        skip = 0
        while True:
            batch = self.get_incidents(skip=skip)
            if not batch:
                break
            all_incidents.extend(batch)
            skip += self.batch_size
            if self.batch_delay > 0:
                time.sleep(self.batch_delay)
        return all_incidents