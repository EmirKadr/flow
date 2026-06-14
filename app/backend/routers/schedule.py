from .schedule_shared import *
from .schedule_calculator_routes import (
    router as calculator_router,
    get_activity_capacity,
    get_activity_capacity_cell,
    get_automatic_calculator_results,
    get_calculator_profile,
    import_calculator_profile,
    update_calculator_profile,
)
from .schedule_mutation_routes import (
    router as mutation_router,
    bulk_update_cells,
    restore_hours,
    split_cell,
    update_cell,
)
from .schedule_productivity_routes import (
    router as productivity_router,
    get_schedule_productivity_summary,
)
from .schedule_query_routes import (
    router as query_router,
    get_schedule,
    get_schedule_presence,
    get_schedule_revision,
)
from .schedule_summary_routes import router as summary_router, get_summary

router = query_router
router.include_router(calculator_router)
router.include_router(productivity_router)
router.include_router(mutation_router)
router.include_router(summary_router)
