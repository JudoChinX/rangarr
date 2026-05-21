INSERT OR REPLACE INTO RootFolders (Id, Path) VALUES (1, '/tmp/media');

INSERT OR REPLACE INTO Tags (Id, Label) VALUES (1, 'test-tag');

INSERT OR REPLACE INTO MovieMetadata (Id, TmdbId, Images, Title, SortTitle, CleanTitle, OriginalTitle, CleanOriginalTitle, Status, Runtime, Recommendations, OriginalLanguage, LastInfoSync, Year, Ratings, Genres, Keywords)
VALUES
(1, 99000001, '[]', 'Test Movie 01', 'test movie 01', 'testmovie01', 'Test Movie 01', 'testmovie01', 3, 120, '[]', 1, '2020-01-01 00:00:00Z', 2020, '{}', '[]', '[]'),
(2, 99000002, '[]', 'Test Movie 02', 'test movie 02', 'testmovie02', 'Test Movie 02', 'testmovie02', 3, 120, '[]', 1, '2020-01-01 00:00:00Z', 2020, '{}', '[]', '[]'),
(3, 99000003, '[]', 'Test Movie 03', 'test movie 03', 'testmovie03', 'Test Movie 03', 'testmovie03', 3, 120, '[]', 1, '2020-01-01 00:00:00Z', 2020, '{}', '[]', '[]'),
(4, 99000004, '[]', 'Test Movie 04', 'test movie 04', 'testmovie04', 'Test Movie 04', 'testmovie04', 3, 120, '[]', 1, '2020-01-01 00:00:00Z', 2020, '{}', '[]', '[]'),
(5, 99000005, '[]', 'Test Movie 05', 'test movie 05', 'testmovie05', 'Test Movie 05', 'testmovie05', 3, 120, '[]', 1, '2020-01-01 00:00:00Z', 2020, '{}', '[]', '[]');

INSERT OR REPLACE INTO Movies (Id, Path, Monitored, QualityProfileId, MovieFileId, MinimumAvailability, MovieMetadataId)
VALUES
(1, '/tmp/media/test-movie-01', 1, 1, 0, 1, 1),
(2, '/tmp/media/test-movie-02', 1, 1, 0, 1, 2),
(3, '/tmp/media/test-movie-03', 1, 1, 0, 1, 3),
(4, '/tmp/media/test-movie-04', 1, 1, 0, 1, 4),
(5, '/tmp/media/test-movie-05', 1, 1, 0, 1, 5);
