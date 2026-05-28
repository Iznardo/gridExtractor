"""GraphQL strings para el script de discovery.

GRID expone conexiones tipo Relay: `edges { node { ... } }` + `pageInfo`.
No usar f-strings con comillas dentro: pasar variables via
`GridGraphQLClient.query_central(query, variables=...)`.
"""

# Busqueda de torneos por nombre. Se filtra en cliente por igualdad exacta
# (StringFilter.contains da matches parciales). La jerarquia de subfases
# (Regular Season, Playoffs...) se maneja en SERIES_BY_TOURNAMENTS con
# `includeChildren`, no aqui.
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


# Paginar series de un torneo incluyendo toda su jerarquia de hijos.
# `SeriesTournamentFilter.includeChildren: { equals: true }` hace que la
# API devuelva series de sub-torneos (fases, semanas...) sin que nosotros
# tengamos que enumerarlos. Filtrar ademas por SeriesType = ESPORTS.
# `orderBy` y `orderDirection` son obligatorios en `allSeries`.
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

# Jugadores de un equipo concreto. NullableIdFilter solo admite un ID a la
# vez, asi que se llama una vez por equipo. El filtro types:[ESPORTS] no
# esta disponible en runtime aunque aparezca en el schema introspectado.
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
