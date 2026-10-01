export function createMusicFilesUiState(pageSize = Number(localStorage.getItem('music-files-page-size') || 50)) {
  return {search:'', genre:'all', detailedGenre:'all', playlist:'all', analysis:'all', artwork:'all', quality:'all', sort:'newest', page:1, pageSize};
}

export function musicFilesQuery(state) {
  return new URLSearchParams({
    paged:'true', page:String(state.page), page_size:String(state.pageSize), search:state.search,
    genre:state.genre, detailed_genre:state.detailedGenre, playlist:state.playlist,
    analysis:state.analysis, artwork:state.artwork, quality:state.quality, sort:state.sort,
  });
}

export function resetMusicFilesFilters(state) {
  Object.assign(state, {search:'',genre:'all',detailedGenre:'all',playlist:'all',analysis:'all',artwork:'all',quality:'all',sort:'newest',page:1});
  return state;
}
