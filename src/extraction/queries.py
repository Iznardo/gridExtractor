"""GraphQL query strings for the official and scrim extractors."""

# Official series of a tournament including its whole child hierarchy.
# workflowStatuses is required by the schema (non-null field). since
# ($since: String) is optional: GRID ignores the filter when it is null.
# Two parent levels are requested to cover most tournament hierarchies.
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

# SCRIM-type series (no tournament filter: download every scrim GRID exposes to
# our account). workflowStatuses is still non-null. since is optional for
# incremental runs.
SCRIM_SERIES = """
query ScrimSeries($since: String, $after: String) {
  allSeries(
    filter: {
      startTimeScheduled: { gte: $since }
      workflowStatuses: [PUBLISHED]
      types: [SCRIM]
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
      }
    }
    pageInfo { hasNextPage endCursor }
  }
}
"""

# A player's role by grid_id. Used by RoleCache to determine the observed role
# in positional reconciliation.
PLAYER_ROLES_BY_ID = """
query PlayerRolesById($pid: ID!) {
  player(id: $pid) {
    id
    nickname
    roles { name }
  }
}
"""
