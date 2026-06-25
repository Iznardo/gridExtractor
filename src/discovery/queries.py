"""GraphQL query strings for the discovery script.

GRID exposes Relay-style connections: `edges { node { ... } }` + `pageInfo`.
Do not inline values with f-strings; pass them through
`GridGraphQLClient.query_central(query, variables=...)`.
"""

# Tournament search by name. Filtered client-side by exact equality
# (StringFilter.contains returns partial matches). The sub-stage hierarchy
# (Regular Season, Playoffs...) is handled in SERIES_BY_TOURNAMENTS via
# `includeChildren`, not here.
TOURNAMENTS_BY_NAME = """
query TournamentsByName($name: String!) {
  tournaments(filter: { name: { contains: $name } }, first: 50) {
    edges {
      node {
        id
        name
      }
    }
    pageInfo {
      hasNextPage
      endCursor
    }
  }
}
"""


# Paginate a tournament's series including its whole child hierarchy.
# `SeriesTournamentFilter.includeChildren: { equals: true }` makes the API
# return series of sub-tournaments (stages, weeks...) without enumerating them.
# Also filters by SeriesType = ESPORTS. `orderBy`/`orderDirection` are required
# on `allSeries`.
SERIES_BY_TOURNAMENTS = """
query SeriesByTournaments($tid: ID!, $after: String) {
  allSeries(
    filter: {
      tournament: { id: { in: [$tid] }, includeChildren: { equals: true } }
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
        teams {
          baseInfo {
            id
            name
            nameShortened
          }
        }
      }
    }
    pageInfo {
      hasNextPage
      endCursor
    }
  }
}
"""

# Players of a single team. NullableIdFilter takes one id at a time, so this is
# called once per team. The types:[ESPORTS] filter is not available at runtime
# even though it appears in the introspected schema.
PLAYERS_BY_TEAM = """
query PlayersByTeam($teamId: ID!, $after: String) {
  players(
    filter: { teamIdFilter: { id: $teamId } }
    first: 25
    after: $after
  ) {
    edges {
      node {
        id
        nickname
        roles {
          name
        }
        team {
          id
        }
      }
    }
    pageInfo {
      hasNextPage
      endCursor
    }
  }
}
"""
