import { z } from 'zod';

export const apiKeySchema = z
  .string({ required_error: 'API key is required.' })
  .trim()
  .min(1, { message: 'API key cannot be empty.' })
  .min(10, { message: 'Please enter a valid API key (too short).' })
  .max(255, { message: 'API key exceeds the maximum allowed length.' });
