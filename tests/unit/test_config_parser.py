"""Tests for config_parser.py configuration validation and schema."""

import re
from typing import Any

import pytest

from rangarr.config_parser import SETTINGS_SCHEMA
from rangarr.config_parser import get_setting_default
from rangarr.config_parser import parse_config
from tests.helpers import assert_config_result

_parse_config_cases = {
    'not_a_dict_string': {
        'config_data': 'not a dict\nanother string',
        'expected_error': 'Configuration file must be a YAML mapping at the top level.',
    },
    'list_instead_of_dict': {
        'config_data': ['list', 'instead', 'of', 'dict'],
        'expected_error': 'Configuration file must be a YAML mapping at the top level.',
    },
    'missing_instances_key': {
        'config_data': {},
        'expected_error': "Missing required top-level key: 'instances'",
    },
    'invalid_run_interval_type': {
        'config_data': {
            'instances': {
                'radarr-main': {
                    'type': 'radarr',
                    'url': 'http://localhost:7878',
                    'api_key': 'radarr_api_key',
                    'enabled': True,
                }
            },
            'global': {'run_interval_minutes': 'not int'},
        },
        'expected_error': "'global.run_interval_minutes' must be of type int.",
    },
    'global_not_a_dict': {
        'config_data': {'instances': {}, 'global': 'not a dict'},
        'expected_error': "'global' must be a YAML mapping.",
    },
    'invalid_interval_type': {
        'config_data': {'instances': {}, 'global': {'interval': '3600'}},
        'expected_error': "'global.interval' must be an integer.",
    },
    'negative_run_interval': {
        'config_data': {
            'instances': {
                'radarr-main': {
                    'type': 'radarr',
                    'url': 'http://localhost:7878',
                    'api_key': 'radarr_api_key',
                    'enabled': True,
                }
            },
            'global': {'run_interval_minutes': -1},
        },
        'expected_error': "'global.run_interval_minutes' must be a non-negative integer.",
    },
    'negative_missing_batch_size': {
        'config_data': {
            'instances': {
                'radarr-main': {
                    'type': 'radarr',
                    'url': 'http://localhost:7878',
                    'api_key': 'radarr_api_key',
                    'enabled': True,
                }
            },
            'global': {'missing_batch_size': -5},
        },
        'expected_error': "'global.missing_batch_size' must be 0 (disabled), -1 (unlimited), or a positive integer.",
    },
    'instances_not_a_dict': {
        'config_data': {'instances': 'not a dict'},
        'expected_error': "'instances' must be a YAML mapping.",
    },
    'instance_not_a_dict': {
        'config_data': {'instances': {'radarr-main': 'not a dict'}},
        'expected_error': "Instance 'radarr-main' must be a YAML mapping.",
    },
    'missing_type_field': {
        'config_data': {
            'instances': {
                'my-instance': {
                    'url': 'http://localhost:7878',
                    'api_key': 'radarr_api_key',
                }
            }
        },
        'expected_error': "Missing 'type' field for instance 'my-instance'.",
    },
    'radarr_missing_url': {
        'config_data': {
            'instances': {
                'radarr-main': {
                    'type': 'radarr',
                    'api_key': 'radarr_api_key',
                }
            }
        },
        'expected_error': "Missing or empty 'url' for instance 'radarr-main'.",
    },
    'sonarr_missing_api_key': {
        'config_data': {
            'instances': {
                'sonarr-tv': {
                    'type': 'sonarr',
                    'url': 'http://localhost:8989',
                }
            }
        },
        'expected_error': "Missing or empty 'api_key' for instance 'sonarr-tv'.",
    },
    'sonarr_empty_api_key': {
        'config_data': {
            'instances': {
                'sonarr-tv': {
                    'type': 'sonarr',
                    'url': 'http://localhost:8989',
                    'api_key': '',
                }
            }
        },
        'expected_error': "Missing or empty 'api_key' for instance 'sonarr-tv'.",
    },
    'radarr_negative_weight': {
        'config_data': {
            'instances': {
                'radarr-4k': {
                    'type': 'radarr',
                    'url': 'http://localhost:7878',
                    'api_key': 'radarr_api_key',
                    'weight': -1,
                    'enabled': True,
                }
            }
        },
        'expected_error': "'weight' for instance 'radarr-4k' must be a positive number.",
    },
    'radarr_invalid_weight_type': {
        'config_data': {
            'instances': {
                'radarr-4k': {
                    'type': 'radarr',
                    'url': 'http://localhost:7878',
                    'api_key': 'radarr_api_key',
                    'weight': 'heavy',
                    'enabled': True,
                }
            }
        },
        'expected_error': "'weight' for instance 'radarr-4k' must be a positive number.",
    },
    'invalid_search_order': {
        'config_data': {
            'instances': {
                'radarr-main': {
                    'type': 'radarr',
                    'url': 'http://localhost:7878',
                    'api_key': 'radarr_api_key',
                    'enabled': True,
                }
            },
            'global': {'search_order': 'sideways'},
        },
        'expected_error': "'global.search_order' must be one of: 'alphabetical_ascending', 'alphabetical_descending', 'last_added_ascending', 'last_added_descending', 'last_searched_ascending', 'last_searched_descending', 'random', 'release_date_ascending', 'release_date_descending'.",
    },
    'mixed_case_instance_type_accepted': {
        'config_data': {
            'instances': {
                'my-movies': {
                    'type': 'Radarr',
                    'url': 'http://localhost:7878',
                    'api_key': 'somekey',
                    'enabled': True,
                }
            }
        },
        'expected_result': {
            'instances': {'radarr': [{'name': 'my-movies'}]},
        },
    },
    'invalid_instance_type': {
        'config_data': {
            'instances': {
                'test': {
                    'type': 'plex',
                    'url': 'http://test',
                    'api_key': 'testkey',
                }
            }
        },
        'expected_error': "Invalid type 'plex' for instance 'test'. Must be one of: radarr, sonarr, lidarr.",
    },
    'empty_instances_dict': {
        'config_data': {'instances': {}},
        'expected_error': "No instances defined under 'instances'. Add at least one Radarr, Sonarr, or Lidarr instance.",
    },
    'missing_batch_size_unlimited': {
        'config_data': {
            'instances': {
                'test-instance': {
                    'type': 'radarr',
                    'host': 'http://test',
                    'api_key': 'test_key',
                    'enabled': True,
                }
            },
            'global': {
                'missing_batch_size': -1,
            },
        },
        'expected_result': {
            'global_settings': {
                'missing_batch_size': -1,
            },
        },
    },
    'upgrade_batch_size_unlimited': {
        'config_data': {
            'instances': {
                'test-instance': {
                    'type': 'radarr',
                    'host': 'http://test',
                    'api_key': 'test_key',
                    'enabled': True,
                }
            },
            'global': {
                'upgrade_batch_size': -1,
            },
        },
        'expected_result': {
            'global_settings': {
                'upgrade_batch_size': -1,
            },
        },
    },
    'missing_batch_size_disabled': {
        'config_data': {
            'instances': {
                'test-instance': {
                    'type': 'radarr',
                    'host': 'http://test',
                    'api_key': 'test_key',
                    'enabled': True,
                }
            },
            'global': {
                'missing_batch_size': 0,
            },
        },
        'expected_result': {
            'global_settings': {
                'missing_batch_size': 0,
            },
        },
    },
    'upgrade_batch_size_disabled': {
        'config_data': {
            'instances': {
                'test-instance': {
                    'type': 'radarr',
                    'host': 'http://test',
                    'api_key': 'test_key',
                    'enabled': True,
                }
            },
            'global': {
                'upgrade_batch_size': 0,
            },
        },
        'expected_result': {
            'global_settings': {
                'upgrade_batch_size': 0,
            },
        },
    },
    'missing_batch_size_invalid_negative_two': {
        'config_data': {
            'instances': {
                'test-instance': {
                    'type': 'radarr',
                    'host': 'http://test',
                    'api_key': 'test_key',
                    'enabled': True,
                }
            },
            'global': {
                'missing_batch_size': -2,
            },
        },
        'expected_error': "'global.missing_batch_size' must be 0 (disabled), -1 (unlimited), or a positive integer.",
    },
    'upgrade_batch_size_invalid_negative_two': {
        'config_data': {
            'instances': {
                'test-instance': {
                    'type': 'radarr',
                    'host': 'http://test',
                    'api_key': 'test_key',
                    'enabled': True,
                }
            },
            'global': {
                'upgrade_batch_size': -2,
            },
        },
        'expected_error': "'global.upgrade_batch_size' must be 0 (disabled), -1 (unlimited), or a positive integer.",
    },
    'stagger_interval_seconds_rejects_zero': {
        'config_data': {
            'instances': {
                'test-instance': {
                    'type': 'radarr',
                    'host': 'http://test',
                    'api_key': 'test_key',
                    'enabled': True,
                }
            },
            'global': {
                'stagger_interval_seconds': 0,
            },
        },
        'expected_error': "'global.stagger_interval_seconds' must be at least 1.",
    },
    'stagger_interval_seconds_rejects_negative': {
        'config_data': {
            'instances': {
                'test-instance': {
                    'type': 'radarr',
                    'host': 'http://test',
                    'api_key': 'test_key',
                    'enabled': True,
                }
            },
            'global': {
                'stagger_interval_seconds': -1,
            },
        },
        'expected_error': "'global.stagger_interval_seconds' must be at least 1.",
    },
    'fetch_page_size_default': {
        'config_data': {
            'instances': {
                'test-instance': {
                    'type': 'radarr',
                    'host': 'http://test',
                    'api_key': 'testkey',
                    'enabled': True,
                }
            },
            'global': {},
        },
        'expected_result': {
            'global_settings': {
                'fetch_page_size': 2000,
            },
        },
    },
    'fetch_page_size_custom': {
        'config_data': {
            'instances': {
                'test-instance': {
                    'type': 'radarr',
                    'host': 'http://test',
                    'api_key': 'testkey',
                    'enabled': True,
                }
            },
            'global': {
                'fetch_page_size': 5000,
            },
        },
        'expected_result': {
            'global_settings': {
                'fetch_page_size': 5000,
            },
        },
    },
    'fetch_page_size_minimum_valid': {
        'config_data': {
            'instances': {
                'test-instance': {
                    'type': 'radarr',
                    'host': 'http://test',
                    'api_key': 'testkey',
                    'enabled': True,
                }
            },
            'global': {
                'fetch_page_size': 1,
            },
        },
        'expected_result': {
            'global_settings': {
                'fetch_page_size': 1,
            },
        },
    },
    'fetch_page_size_rejects_zero': {
        'config_data': {
            'instances': {
                'test-instance': {
                    'type': 'radarr',
                    'host': 'http://test',
                    'api_key': 'testkey',
                    'enabled': True,
                }
            },
            'global': {
                'fetch_page_size': 0,
            },
        },
        'expected_error': "'global.fetch_page_size' must be at least 1.",
    },
    'fetch_page_size_rejects_negative': {
        'config_data': {
            'instances': {
                'test-instance': {
                    'type': 'radarr',
                    'host': 'http://test',
                    'api_key': 'testkey',
                    'enabled': True,
                }
            },
            'global': {
                'fetch_page_size': -1,
            },
        },
        'expected_error': "'global.fetch_page_size' must be at least 1.",
    },
    'fetch_page_size_rejects_wrong_type': {
        'config_data': {
            'instances': {
                'test-instance': {
                    'type': 'radarr',
                    'host': 'http://test',
                    'api_key': 'testkey',
                    'enabled': True,
                }
            },
            'global': {
                'fetch_page_size': '1000',
            },
        },
        'expected_error': "'global.fetch_page_size' must be of type int.",
    },
    'retry_interval_days_rejects_negative': {
        'config_data': {
            'instances': {
                'test-instance': {
                    'type': 'radarr',
                    'host': 'http://test',
                    'api_key': 'test_key',
                    'enabled': True,
                }
            },
            'global': {
                'retry_interval_days': -1,
            },
        },
        'expected_error': 'must be a non-negative integer',
    },
    'all_instances_implicit_disabled': {
        'config_data': {
            'instances': {
                'radarr-main': {
                    'type': 'radarr',
                    'url': 'http://localhost:7878',
                    'api_key': 'radarr_api_key',
                },
                'sonarr-tv': {
                    'type': 'sonarr',
                    'url': 'http://localhost:8989',
                    'api_key': 'sonarr_api_key',
                },
            }
        },
        'expected_error': "No instances defined under 'instances'. Add at least one Radarr, Sonarr, or Lidarr instance.",
    },
    'yaml_style_mapping': {
        'config_data': {
            'global': {'interval': 3600},
            'instances': {
                'sonarr-main': {
                    'type': 'sonarr',
                    'host': 'http://sonarr:8989',
                    'api_key': 'abc',
                    'enabled': True,
                },
                'my-radarr': {
                    'type': 'radarr',
                    'url': 'http://radarr:7878',
                    'api_key': 'def',
                    'enabled': False,
                },
            },
        },
        'expected_result': {
            'global_settings': {
                'run_interval_minutes': 60,
                'dry_run': False,
            },
            'instances': {
                'sonarr': [
                    {
                        'name': 'sonarr-main',
                        'url': 'http://sonarr:8989',
                        'api_key': 'abc',
                    }
                ],
                'radarr': [],
            },
        },
    },
    'valid_basic': {
        'config_data': {
            'instances': {
                'my-movies': {
                    'type': 'radarr',
                    'url': 'http://localhost:7878',
                    'api_key': 'somekey',
                    'enabled': True,
                },
                'my-tv': {
                    'type': 'sonarr',
                    'url': 'http://localhost:8989',
                    'api_key': 'anotherkey',
                    'enabled': True,
                },
                'my-music': {
                    'type': 'lidarr',
                    'url': 'http://localhost:8686',
                    'api_key': 'lidarrkey',
                    'enabled': True,
                },
            }
        },
        'expected_result': {
            'global_settings': {
                'run_interval_minutes': 60,
                'stagger_interval_seconds': 30,
                'retry_interval_days': 30,
                'search_order': 'last_searched_ascending',
                'dry_run': False,
            },
            'instances': {
                'radarr': [
                    {
                        'name': 'my-movies',
                        'weight': 1,
                    }
                ],
                'sonarr': [
                    {
                        'name': 'my-tv',
                        'weight': 1,
                    }
                ],
                'lidarr': [
                    {
                        'name': 'my-music',
                        'url': 'http://localhost:8686',
                        'api_key': 'lidarrkey',
                        'enabled': True,
                        'weight': 1,
                    }
                ],
            },
        },
    },
    'valid_overrides': {
        'config_data': {
            'global': {'run_interval_minutes': 30, 'missing_batch_size': 100},
            'instances': {
                'ultra-hd-movies': {
                    'type': 'radarr',
                    'url': 'http://localhost:7878',
                    'api_key': 'x',
                    'enabled': True,
                    'weight': 2.5,
                }
            },
        },
        'expected_result': {
            'global_settings': {
                'run_interval_minutes': 30,
                'missing_batch_size': 100,
                'stagger_interval_seconds': 30,
                'retry_interval_days': 30,
                'search_order': 'last_searched_ascending',
                'dry_run': False,
            },
            'instances': {
                'radarr': [{'name': 'ultra-hd-movies', 'weight': 2.5}],
            },
        },
    },
    'interleave_instances_defaults_to_false': {
        'config_data': {
            'instances': {
                'test-radarr': {
                    'type': 'radarr',
                    'url': 'http://localhost:7878',
                    'api_key': 'testkey',
                    'enabled': True,
                }
            },
        },
        'expected_result': {
            'global_settings': {
                'interleave_instances': False,
            },
        },
    },
    'interleave_instances_accepts_true': {
        'config_data': {
            'instances': {
                'test-radarr': {
                    'type': 'radarr',
                    'url': 'http://localhost:7878',
                    'api_key': 'testkey',
                    'enabled': True,
                }
            },
            'global': {'interleave_instances': True},
        },
        'expected_result': {
            'global_settings': {
                'interleave_instances': True,
            },
        },
    },
    'interleave_instances_rejects_non_bool': {
        'config_data': {
            'instances': {
                'test-radarr': {
                    'type': 'radarr',
                    'url': 'http://localhost:7878',
                    'api_key': 'testkey',
                    'enabled': True,
                }
            },
            'global': {'interleave_instances': 'yes'},
        },
        'expected_error': "'global.interleave_instances' must be of type bool.",
    },
    'interleave_types_defaults_to_true': {
        'config_data': {
            'instances': {
                'test-radarr': {
                    'type': 'radarr',
                    'url': 'http://test',
                    'api_key': 'testkey',
                    'enabled': True,
                }
            },
        },
        'expected_result': {
            'global_settings': {
                'interleave_types': True,
            },
        },
    },
    'interleave_types_accepts_false': {
        'config_data': {
            'instances': {
                'test-radarr': {
                    'type': 'radarr',
                    'url': 'http://test',
                    'api_key': 'testkey',
                    'enabled': True,
                }
            },
            'global': {'interleave_types': False},
        },
        'expected_result': {
            'global_settings': {
                'interleave_types': False,
            },
        },
    },
    'interleave_types_rejects_non_bool': {
        'config_data': {
            'instances': {
                'test-radarr': {
                    'type': 'radarr',
                    'url': 'http://test',
                    'api_key': 'testkey',
                    'enabled': True,
                }
            },
            'global': {'interleave_types': 'yes'},
        },
        'expected_error': "'global.interleave_types' must be of type bool.",
    },
    'season_packs_defaults_to_false': {
        'config_data': {
            'instances': {
                'test-sonarr': {
                    'type': 'sonarr',
                    'url': 'http://localhost:8989',
                    'api_key': 'testkey',
                    'enabled': True,
                }
            },
        },
        'expected_result': {
            'global_settings': {
                'season_packs': False,
            },
        },
    },
    'season_packs_accepts_false': {
        'config_data': {
            'instances': {
                'test-sonarr': {
                    'type': 'sonarr',
                    'url': 'http://localhost:8989',
                    'api_key': 'testkey',
                    'enabled': True,
                }
            },
            'global': {'season_packs': False},
        },
        'expected_result': {
            'global_settings': {
                'season_packs': False,
            },
        },
    },
    'season_packs_accepts_float_ratio': {
        'config_data': {
            'instances': {
                'test-sonarr': {
                    'type': 'sonarr',
                    'url': 'http://localhost:8989',
                    'api_key': 'testkey',
                    'enabled': True,
                }
            },
            'global': {'season_packs': 0.3},
        },
        'expected_result': {
            'global_settings': {
                'season_packs': 0.3,
            },
        },
    },
    'season_packs_accepts_int_count': {
        'config_data': {
            'instances': {
                'test-sonarr': {
                    'type': 'sonarr',
                    'url': 'http://localhost:8989',
                    'api_key': 'testkey',
                    'enabled': True,
                }
            },
            'global': {'season_packs': 3},
        },
        'expected_result': {
            'global_settings': {
                'season_packs': 3,
            },
        },
    },
    'season_packs_accepts_true': {
        'config_data': {
            'instances': {
                'test-sonarr': {
                    'type': 'sonarr',
                    'url': 'http://localhost:8989',
                    'api_key': 'testkey',
                    'enabled': True,
                }
            },
            'global': {'season_packs': True},
        },
        'expected_result': {
            'global_settings': {
                'season_packs': True,
            },
        },
    },
    'season_packs_rejects_float_above_one': {
        'config_data': {
            'instances': {
                'test-sonarr': {
                    'type': 'sonarr',
                    'url': 'http://localhost:8989',
                    'api_key': 'testkey',
                    'enabled': True,
                }
            },
            'global': {'season_packs': 1.5},
        },
        'expected_error': "'global.season_packs' float must be between 0.0 and 1.0 (exclusive).",
    },
    'season_packs_rejects_float_one': {
        'config_data': {
            'instances': {
                'test-sonarr': {
                    'type': 'sonarr',
                    'url': 'http://localhost:8989',
                    'api_key': 'testkey',
                    'enabled': True,
                }
            },
            'global': {'season_packs': 1.0},
        },
        'expected_error': "'global.season_packs' float must be between 0.0 and 1.0 (exclusive).",
    },
    'season_packs_rejects_float_zero': {
        'config_data': {
            'instances': {
                'test-sonarr': {
                    'type': 'sonarr',
                    'url': 'http://localhost:8989',
                    'api_key': 'testkey',
                    'enabled': True,
                }
            },
            'global': {'season_packs': 0.0},
        },
        'expected_error': "'global.season_packs' float must be between 0.0 and 1.0 (exclusive).",
    },
    'season_packs_rejects_int_negative': {
        'config_data': {
            'instances': {
                'test-sonarr': {
                    'type': 'sonarr',
                    'url': 'http://localhost:8989',
                    'api_key': 'testkey',
                    'enabled': True,
                }
            },
            'global': {'season_packs': -1},
        },
        'expected_error': "'global.season_packs' integer must be >= 1.",
    },
    'season_packs_rejects_int_zero': {
        'config_data': {
            'instances': {
                'test-sonarr': {
                    'type': 'sonarr',
                    'url': 'http://localhost:8989',
                    'api_key': 'testkey',
                    'enabled': True,
                }
            },
            'global': {'season_packs': 0},
        },
        'expected_error': "'global.season_packs' integer must be >= 1.",
    },
    'season_packs_rejects_non_bool': {
        'config_data': {
            'instances': {
                'test-sonarr': {
                    'type': 'sonarr',
                    'url': 'http://localhost:8989',
                    'api_key': 'testkey',
                    'enabled': True,
                }
            },
            'global': {'season_packs': []},
        },
        'expected_error': "'global.season_packs' must be a bool, integer >= 1, or float between 0.0 and 1.0.",
    },
    'season_packs_rejects_string': {
        'config_data': {
            'instances': {
                'test-sonarr': {
                    'type': 'sonarr',
                    'url': 'http://localhost:8989',
                    'api_key': 'testkey',
                    'enabled': True,
                }
            },
            'global': {'season_packs': 'yes'},
        },
        'expected_error': "'global.season_packs' must be a bool, integer >= 1, or float between 0.0 and 1.0.",
    },
    'include_tags_defaults_to_empty_list': {
        'config_data': {
            'instances': {
                'test-inst': {
                    'type': 'radarr',
                    'host': 'http://test',
                    'api_key': 'testkey',
                    'enabled': True,
                }
            },
        },
        'expected_result': {
            'global_settings': {
                'include_tags': [],
            },
        },
    },
    'exclude_tags_defaults_to_empty_list': {
        'config_data': {
            'instances': {
                'test-inst': {
                    'type': 'radarr',
                    'host': 'http://test',
                    'api_key': 'testkey',
                    'enabled': True,
                }
            },
        },
        'expected_result': {
            'global_settings': {
                'exclude_tags': [],
            },
        },
    },
    'include_tags_accepts_valid_list': {
        'config_data': {
            'instances': {
                'test-inst': {
                    'type': 'radarr',
                    'host': 'http://test',
                    'api_key': 'testkey',
                    'enabled': True,
                }
            },
            'global': {'include_tags': ['alpha', 'beta']},
        },
        'expected_result': {
            'global_settings': {
                'include_tags': ['alpha', 'beta'],
            },
        },
    },
    'exclude_tags_accepts_valid_list': {
        'config_data': {
            'instances': {
                'test-inst': {
                    'type': 'radarr',
                    'host': 'http://test',
                    'api_key': 'testkey',
                    'enabled': True,
                }
            },
            'global': {'exclude_tags': ['gamma']},
        },
        'expected_result': {
            'global_settings': {
                'exclude_tags': ['gamma'],
            },
        },
    },
    'include_tags_rejects_non_list': {
        'config_data': {
            'instances': {
                'test-inst': {
                    'type': 'radarr',
                    'host': 'http://test',
                    'api_key': 'testkey',
                    'enabled': True,
                }
            },
            'global': {'include_tags': 'alpha'},
        },
        'expected_error': "'global.include_tags' must be of type list.",
    },
    'exclude_tags_rejects_non_list': {
        'config_data': {
            'instances': {
                'test-inst': {
                    'type': 'radarr',
                    'host': 'http://test',
                    'api_key': 'testkey',
                    'enabled': True,
                }
            },
            'global': {'exclude_tags': 42},
        },
        'expected_error': "'global.exclude_tags' must be of type list.",
    },
    'include_tags_rejects_non_string_element': {
        'config_data': {
            'instances': {
                'test-inst': {
                    'type': 'radarr',
                    'host': 'http://test',
                    'api_key': 'testkey',
                    'enabled': True,
                }
            },
            'global': {'include_tags': [99]},
        },
        'expected_error': "'global.include_tags' must be a list of str values.",
    },
    'include_tags_rejects_empty_string_element': {
        'config_data': {
            'instances': {
                'test-inst': {
                    'type': 'radarr',
                    'host': 'http://test',
                    'api_key': 'testkey',
                    'enabled': True,
                }
            },
            'global': {'include_tags': ['']},
        },
        'expected_error': "'global.include_tags' entries must not be empty strings.",
    },
    'exclude_tags_rejects_empty_string_element': {
        'config_data': {
            'instances': {
                'test-inst': {
                    'type': 'radarr',
                    'host': 'http://test',
                    'api_key': 'testkey',
                    'enabled': True,
                }
            },
            'global': {'exclude_tags': ['']},
        },
        'expected_error': "'global.exclude_tags' entries must not be empty strings.",
    },
    'retry_interval_days_overrides_default_to_none': {
        'config_data': {
            'instances': {
                'test-inst': {
                    'type': 'radarr',
                    'host': 'http://test',
                    'api_key': 'testkey',
                    'enabled': True,
                }
            },
        },
        'expected_result': {
            'global_settings': {'retry_interval_days_missing': None, 'retry_interval_days_upgrade': None}
        },
    },
    'retry_interval_days_missing_accepts_int': {
        'config_data': {
            'instances': {
                'test-inst': {
                    'type': 'radarr',
                    'host': 'http://test',
                    'api_key': 'testkey',
                    'enabled': True,
                }
            },
            'global': {'retry_interval_days_missing': 7, 'retry_interval_days_upgrade': 14},
        },
        'expected_result': {'global_settings': {'retry_interval_days_missing': 7, 'retry_interval_days_upgrade': 14}},
    },
    'retry_interval_days_missing_rejects_non_int': {
        'config_data': {
            'instances': {
                'test-inst': {
                    'type': 'radarr',
                    'host': 'http://test',
                    'api_key': 'testkey',
                    'enabled': True,
                }
            },
            'global': {'retry_interval_days_missing': 'weekly'},
        },
        'expected_error': "'global.retry_interval_days_missing' must be of type int",
    },
    'invalid_interval_missing_type': {
        'config_data': {'instances': {}, 'global': {'interval_missing': '3600'}},
        'expected_error': "'global.interval_missing' must be an integer.",
    },
    'interval_missing_rejects_sub_60': {
        'config_data': {'instances': {}, 'global': {'interval_missing': 30}},
        'expected_error': "'global.interval_missing' must be at least 60 seconds.",
    },
    'invalid_interval_upgrade_type': {
        'config_data': {'instances': {}, 'global': {'interval_upgrade': 'daily'}},
        'expected_error': "'global.interval_upgrade' must be an integer.",
    },
    'interval_upgrade_rejects_sub_60': {
        'config_data': {'instances': {}, 'global': {'interval_upgrade': 59}},
        'expected_error': "'global.interval_upgrade' must be at least 60 seconds.",
    },
    'interval_missing_converts_to_minutes': {
        'config_data': {
            'instances': {
                'test-inst': {
                    'type': 'radarr',
                    'host': 'http://test',
                    'api_key': 'testkey',
                    'enabled': True,
                }
            },
            'global': {'interval_missing': 3600},
        },
        'expected_result': {
            'global_settings': {'run_interval_minutes_missing': 60},
        },
    },
    'interval_upgrade_converts_to_minutes': {
        'config_data': {
            'instances': {
                'test-inst': {
                    'type': 'radarr',
                    'host': 'http://test',
                    'api_key': 'testkey',
                    'enabled': True,
                }
            },
            'global': {'interval_upgrade': 21600},
        },
        'expected_result': {
            'global_settings': {'run_interval_minutes_upgrade': 360},
        },
    },
    'interval_missing_upgrade_defaults_to_none': {
        'config_data': {
            'instances': {
                'test-inst': {
                    'type': 'radarr',
                    'host': 'http://test',
                    'api_key': 'testkey',
                    'enabled': True,
                }
            },
        },
        'expected_result': {
            'global_settings': {
                'run_interval_minutes_missing': None,
                'run_interval_minutes_upgrade': None,
            },
        },
    },
}


@pytest.mark.parametrize(
    'config_data, expected_error, expected_result',
    [
        (
            case['config_data'],
            case.get('expected_error'),
            case.get('expected_result'),
        )
        for case in _parse_config_cases.values()
    ],
    ids=list(_parse_config_cases.keys()),
)
def test_parse_config(config_data: Any, expected_error: Any, expected_result: Any) -> None:
    """Test parse_config validates configuration structure and values."""
    if expected_error:
        with pytest.raises(ValueError, match=re.escape(expected_error)):
            parse_config(config_data)
    else:
        assert_config_result(parse_config(config_data), expected_result)


def test_get_setting_default_returns_schema_values() -> None:
    """Test get_setting_default returns values consistent with SETTINGS_SCHEMA."""
    for setting, definition in SETTINGS_SCHEMA.items():
        assert get_setting_default(setting) == definition['default']


def test_get_setting_default_raises_on_invalid_setting() -> None:
    """Test get_setting_default raises KeyError for undefined settings."""
    with pytest.raises(KeyError):
        get_setting_default('nonexistent_setting')
