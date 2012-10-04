// Copyright (c) 2012 The Chromium Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

// Defines all the "cc" command-line switches.

#ifndef CC_SWITCHES_H_
#define CC_SWITCHES_H_

#include "build/build_config.h"
#include "webkit/glue/webkit_glue_export.h"

// Since cc is used from the render process, anything that goes here also needs
// to be added to render_process_host_impl.cc.

namespace cc {
namespace switches {

WEBKIT_GLUE_EXPORT extern const char kJankInsteadOfCheckerboard[];
WEBKIT_GLUE_EXPORT extern const char kBackgroundColorInsteadOfCheckerboard[];

}  // namespace switches
}  // namespace cc

#endif  // CC_SWITCHES_H_
