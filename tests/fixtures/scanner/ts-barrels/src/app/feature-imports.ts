// AC-2.2: a workspace-package import (``@demo/ui``) and a ``paths`` alias with
// ``*`` (``@shared/*``) both reach an external package through barrels.
import { announce } from '@demo/ui';
import { track } from '@shared/analytics';
import { Button, inject as uiInject } from './barrel';

announce('saved');
uiInject(TOKEN);
track('event');
const b: Button = {};
