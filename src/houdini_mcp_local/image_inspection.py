"""Visual warnings are independent of successful renderer/file completion."""


def inspect_pixels(rgb, alpha=None):
    # NumPy is supplied by the supported Houdini Python runtime; MCP does not import it.
    import numpy as np
    color = np.asarray(rgb, dtype=np.float32)
    if color.size == 0 or color.size % 3:
        raise ValueError('Expected nonempty RGB pixels')
    color = color.reshape(-1, 3)
    finite = bool(np.isfinite(color).all())
    if not finite:
        return {'finite': False, 'warnings': ['nonfinite_pixels'], 'classification': 'invalid'}
    peak = float(np.max(np.abs(color)))
    spread = float(np.max(np.ptp(color, axis=0)))
    warnings = []
    if peak <= 1e-6:
        warnings.append('all_black_or_empty')
    elif spread <= 1e-6:
        warnings.append('uniform_color')
    opacity = None
    if alpha is not None:
        a = np.asarray(alpha, dtype=np.float32)
        if not np.isfinite(a).all():
            return {'finite': False, 'warnings': ['nonfinite_alpha'], 'classification': 'invalid'}
        opacity = float(np.max(a)) if a.size else 0.0
        if opacity <= 1e-6:
            warnings.append('fully_transparent')
    return {'finite': True, 'classification': 'warning' if warnings else 'content_present',
            'warnings': warnings, 'mean_rgb': color.mean(axis=0, dtype=np.float64).tolist(),
            'max_abs_rgb': peak, 'max_channel_range': spread, 'max_alpha': opacity,
            'note': 'Content statistics are not artistic acceptance; intentional black or uniform frames may be valid.'}
