"""GraphQL strings para el extractor de partidos oficiales."""

# Series oficiales de un torneo incluyendo toda su jerarquia de hijos.
# workflowStatuses es obligatorio en el schema (campo non-null).
# since ($since: String) es opcional: cuando es null GRID ignora el filtro.
# Se piden 2 niveles de parent para cubrir la mayoria de jerarquias de torneo.
OFFICIAL_SERIES_BY_TOURNAMENT = """
query OfficialSeriesByTournament($tid: ID!, $since: String, $after: String) {
  allSeries(
    filter: {
      tournament: { id: { in: [$tid] }, includeChildren: { equals: true } }
      startTimeScheduled: { gte: $since }
      workflowStatuses: [PUBLISHED]
      types: [ESPORTS]
    }
    first: 50
    after: $after
    orderBy: StartTimeScheduled
    orderDirection: ASC
  ) {
    edges {
      node {
        id
        startTimeScheduled
        format { nameShortened }
        teams {
          baseInfo { id name nameShortened }
        }
        tournament {
          id
          name
          parent {
            id
            name
            parent { id name }
          }
        }
      }
    }
    pageInfo { hasNextPage endCursor }
  }
}
"""

# Rol de un jugador por su grid_id. Se usa en RoleCache para determinar
# el rol observado en la reconciliacion posicional (CLAUDE.md §5.5).
PLAYER_ROLES_BY_ID = """
query PlayerRolesById($pid: ID!) {
  player(id: $pid) {
    id
    nickname
    roles { name }
  }
}
"""
