"""Data-to-AI Foundations: a small, dependency-free reference implementation.

The package separates the parts of a data pipeline that repeat from one AI
application to the next (reading sources, aligning them in time, checking
quality, delivering a table, reporting on the run) from the parts that change
(the domain rules), which live in a configuration file.
"""

from .pipeline import RunResult, run_pipeline

__all__ = ["RunResult", "run_pipeline"]
__version__ = "0.1.0"
