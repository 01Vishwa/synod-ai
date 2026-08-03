export type ErrorCode =
  | 'VALIDATION_ERROR'
  | 'AUTHENTICATION_ERROR'
  | 'AUTHORIZATION_ERROR'
  | 'NETWORK_ERROR'
  | 'TIMEOUT_ERROR'
  | 'PROVIDER_ERROR'
  | 'RATE_LIMIT_ERROR'
  | 'SERVER_ERROR'
  | 'UNKNOWN_ERROR';

export class AppError extends Error {
  constructor(
    public message: string,
    public code: ErrorCode,
    public originalError?: unknown
  ) {
    super(message);
    this.name = 'AppError';
  }
}

export class ValidationError extends AppError {
  constructor(message: string = 'Validation failed', originalError?: unknown) {
    super(message, 'VALIDATION_ERROR', originalError);
    this.name = 'ValidationError';
  }
}

export class AuthenticationError extends AppError {
  constructor(message: string = 'Authentication failed. Please verify your credentials.', originalError?: unknown) {
    super(message, 'AUTHENTICATION_ERROR', originalError);
    this.name = 'AuthenticationError';
  }
}

export class AuthorizationError extends AppError {
  constructor(message: string = 'You do not have permission to perform this action.', originalError?: unknown) {
    super(message, 'AUTHORIZATION_ERROR', originalError);
    this.name = 'AuthorizationError';
  }
}

export class NetworkError extends AppError {
  constructor(message: string = 'Unable to connect. Check your internet connection.', originalError?: unknown) {
    super(message, 'NETWORK_ERROR', originalError);
    this.name = 'NetworkError';
  }
}

export class TimeoutError extends AppError {
  constructor(message: string = 'Request timed out. Please try again.', originalError?: unknown) {
    super(message, 'TIMEOUT_ERROR', originalError);
    this.name = 'TimeoutError';
  }
}

export class ProviderError extends AppError {
  constructor(message: string = 'Provider is temporarily unavailable.', originalError?: unknown) {
    super(message, 'PROVIDER_ERROR', originalError);
    this.name = 'ProviderError';
  }
}

export class RateLimitError extends AppError {
  constructor(message: string = 'Too many requests. Please wait and try again.', originalError?: unknown) {
    super(message, 'RATE_LIMIT_ERROR', originalError);
    this.name = 'RateLimitError';
  }
}

export class ServerError extends AppError {
  constructor(message: string = 'Something went wrong on our servers.', originalError?: unknown) {
    super(message, 'SERVER_ERROR', originalError);
    this.name = 'ServerError';
  }
}

export class UnknownError extends AppError {
  constructor(message: string = 'An unexpected error occurred.', originalError?: unknown) {
    super(message, 'UNKNOWN_ERROR', originalError);
    this.name = 'UnknownError';
  }
}

/**
 * Maps raw HTTP responses and exceptions into user-friendly AppErrors.
 * Prevents internal details, JSON, and stack traces from leaking to the UI.
 * Technical details are logged to the console for developers.
 */
export function mapApiError(error: unknown): AppError {
  // Log developer details
  if (process.env.NODE_ENV !== 'production') {
    console.error('[API Error]', error);
  } else {
    console.error('An error occurred during an API request.');
  }

  // Handle standard JS network errors
  if (error instanceof TypeError && error.message === 'Failed to fetch') {
    return new NetworkError();
  }
  
  if (error instanceof Error && error.name === 'AbortError') {
    return new TimeoutError();
  }

  // Handle existing internal ApiError object from fetch wrapper
  if (error && typeof error === 'object' && 'name' in error && error.name === 'ApiError') {
    const apiErr = error as unknown as { status: number; statusText: string; body: string };
    
    switch (apiErr.status) {
      case 400:
      case 422: {
        let message = 'Invalid request data.';
        try {
          const body = JSON.parse(apiErr.body);
          // Custom backend format: { error: { message, details: { fields: {...} } } }
          const fields = body?.error?.details?.fields;
          if (fields && typeof fields === 'object') {
            const msgs = (Object.values(fields) as string[][]).flat();
            if (msgs.length > 0) {
              // Strip Pydantic's "Value error, " prefix for cleaner UI messages
              message = msgs
                .map((m: string) => m.replace(/^Value error,\s*/, ''))
                .join(' ');
            }
          } else if (
            body?.error?.message &&
            body.error.message !== 'Request validation failed.'
          ) {
            message = body.error.message;
          } else if (Array.isArray(body?.detail)) {
            message = (body.detail as Array<{ msg: string; loc?: string[] }>)
              .map((e) =>
                e.loc?.length ? `${e.loc.slice(-1)[0]}: ${e.msg}` : e.msg
              )
              .join('. ');
          } else if (typeof body?.detail === 'string') {
            message = body.detail;
          }
        } catch {
          // JSON parse failed — keep generic message
        }
        return new ValidationError(message, apiErr);
      }
      case 401:
        return new AuthenticationError(undefined, apiErr);
      case 403:
        return new AuthorizationError(undefined, apiErr);
      case 404:
        return new AppError('Resource not found.', 'UNKNOWN_ERROR', apiErr);
      case 408:
        return new TimeoutError(undefined, apiErr);
      case 409:
        return new AppError('Resource already exists.', 'UNKNOWN_ERROR', apiErr);
      case 429:
        return new RateLimitError(undefined, apiErr);
      case 500:
        return new ServerError(undefined, apiErr);
      case 502:
        return new ServerError('Service temporarily unavailable.', apiErr);
      case 503:
        return new ProviderError(undefined, apiErr);
      default:
        return new UnknownError(`Unexpected error (${apiErr.status}).`, apiErr);
    }
  }

  // If it's already an AppError, return it
  if (error instanceof AppError) {
    return error;
  }

  // Default fallback
  return new UnknownError('An unknown error occurred.', error);
}
