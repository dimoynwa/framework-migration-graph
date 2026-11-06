// AC-2.3: a chain of exactly MAX_DEPTH (10) still resolves; one hop more is a
// ``barrel_depth`` diagnostic and records nothing.
import { deepAllowed } from '../deep/ok0';
import { deepTooFar } from '../deep/deep0';

deepAllowed(TOKEN);
deepTooFar(TOKEN);
