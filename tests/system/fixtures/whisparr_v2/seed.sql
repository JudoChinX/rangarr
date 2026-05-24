INSERT OR REPLACE INTO RootFolders (Id, Path) VALUES (1, '/tmp/media');

INSERT OR REPLACE INTO Tags (Id, Label) VALUES (1, 'test-tag');

INSERT OR REPLACE INTO Series (Id, TvdbId, Title, TitleSlug, CleanTitle, Status, Images, Path, Monitored, QualityProfileId, Runtime, UseSceneNumbering, Seasons, Ratings, OriginalLanguage, MonitorNewItems, SeriesType)
VALUES
(1, 10000001, 'Test Performer One', 'test-performer-one', 'testperformerone', 1, '[]', '/tmp/media/test-performer-one', 1, 1, 30, 0, '[]', '{}', 1, 0, 0),
(2, 10000002, 'Test Performer Two', 'test-performer-two', 'testperformertwo', 1, '[]', '/tmp/media/test-performer-two', 1, 1, 30, 0, '[]', '{}', 1, 0, 0),
(3, 10000003, 'Test Performer Three', 'test-performer-three', 'testperformerthree', 1, '[]', '/tmp/media/test-performer-three', 1, 1, 30, 0, '[]', '{}', 1, 0, 0);

INSERT OR REPLACE INTO Episodes (Id, Monitored, SeriesId, SeasonNumber, Title, Runtime, EpisodeFileId, AirDate, AirDateUtc)
VALUES
(1, 1, 1, 1, 'Test Scene 01', 30, 0, '2024-01-15', '2024-01-15T00:00:00Z'),
(2, 1, 2, 1, 'Test Scene 02', 30, 0, '2024-02-10', '2024-02-10T00:00:00Z'),
(3, 1, 3, 1, 'Test Scene 03', 30, 0, '2024-03-05', '2024-03-05T00:00:00Z');
