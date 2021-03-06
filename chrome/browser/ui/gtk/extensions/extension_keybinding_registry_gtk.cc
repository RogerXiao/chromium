// Copyright (c) 2012 The Chromium Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

#include "chrome/browser/ui/gtk/extensions/extension_keybinding_registry_gtk.h"

#include <gtk/gtk.h>

#include "chrome/browser/extensions/api/commands/command_service.h"
#include "chrome/browser/extensions/extension_service.h"
#include "chrome/browser/profiles/profile.h"
#include "extensions/common/extension.h"
#include "ui/base/accelerators/platform_accelerator_gtk.h"

// static
void extensions::ExtensionKeybindingRegistry::SetShortcutHandlingSuspended(
    bool suspended) {
  ExtensionKeybindingRegistryGtk::set_shortcut_handling_suspended(suspended);
}

bool ExtensionKeybindingRegistryGtk::shortcut_handling_suspended_ = false;

ExtensionKeybindingRegistryGtk::ExtensionKeybindingRegistryGtk(
    Profile* profile,
    gfx::NativeWindow window,
    ExtensionFilter extension_filter,
    Delegate* delegate)
    : ExtensionKeybindingRegistry(profile, extension_filter, delegate),
      profile_(profile),
      window_(window),
      accel_group_(NULL) {
  Init();
}

ExtensionKeybindingRegistryGtk::~ExtensionKeybindingRegistryGtk() {
  if (accel_group_) {
    gtk_accel_group_disconnect(accel_group_,
                               NULL);  // Remove all closures.
    event_targets_.clear();

    gtk_window_remove_accel_group(window_, accel_group_);
    g_object_unref(accel_group_);
    accel_group_ = NULL;
  }
}

gboolean ExtensionKeybindingRegistryGtk::HasPriorityHandler(
    const GdkEventKey* event) const {
  if (shortcut_handling_suspended_)
    return FALSE;

  ui::Accelerator accelerator = ui::AcceleratorForGdkKeyCodeAndModifier(
      event->keyval, static_cast<GdkModifierType>(event->state));

  return event_targets_.find(accelerator) != event_targets_.end();
}

void ExtensionKeybindingRegistryGtk::AddExtensionKeybinding(
    const extensions::Extension* extension,
    const std::string& command_name) {
  extensions::CommandService* command_service =
      extensions::CommandService::Get(profile_);
  extensions::CommandMap commands;
  command_service->GetNamedCommands(
          extension->id(),
          extensions::CommandService::ACTIVE_ONLY,
          extensions::CommandService::REGULAR,
          &commands);

  for (extensions::CommandMap::const_iterator iter = commands.begin();
       iter != commands.end(); ++iter) {
    if (!command_name.empty() && (iter->second.command_name() != command_name))
      continue;

    ui::Accelerator accelerator(iter->second.accelerator());
    event_targets_[accelerator].push_back(
        std::make_pair(extension->id(), iter->second.command_name()));

    // Shortcuts except media keys have only one target in the list. See comment
    // about |event_targets_|.
    if (!extensions::CommandService::IsMediaKey(iter->second.accelerator()))
      DCHECK_EQ(1u, event_targets_[accelerator].size());

    if (!accel_group_) {
      accel_group_ = gtk_accel_group_new();
      gtk_window_add_accel_group(window_, accel_group_);
    }

    gtk_accel_group_connect(
        accel_group_,
        ui::GetGdkKeyCodeForAccelerator(accelerator),
        ui::GetGdkModifierForAccelerator(accelerator),
        GtkAccelFlags(0),
        g_cclosure_new(G_CALLBACK(OnGtkAcceleratorThunk), this, NULL));
  }

  // Unlike on Windows, we need to explicitly add the browser action and page
  // action to the event_targets_, even though we don't register them as
  // handlers. See http://crbug.com/124873.
  extensions::Command browser_action;
  if (command_service->GetBrowserActionCommand(
          extension->id(),
          extensions::CommandService::ACTIVE_ONLY,
          &browser_action,
          NULL)) {
    ui::Accelerator accelerator(browser_action.accelerator());
    event_targets_[accelerator].push_back(
        std::make_pair(extension->id(), browser_action.command_name()));
    // We should have only one target. See comment about |event_targets_|.
    DCHECK_EQ(1u, event_targets_[accelerator].size());
  }

  // Add the Page Action (if any).
  extensions::Command page_action;
  if (command_service->GetPageActionCommand(
          extension->id(),
          extensions::CommandService::ACTIVE_ONLY,
          &page_action,
          NULL)) {
    ui::Accelerator accelerator(page_action.accelerator());
    event_targets_[accelerator].push_back(
        std::make_pair(extension->id(), page_action.command_name()));
    // We should have only one target. See comment about |event_targets_|.
    DCHECK_EQ(1u, event_targets_[accelerator].size());
  }
}

void ExtensionKeybindingRegistryGtk::RemoveExtensionKeybindingImpl(
    const ui::Accelerator& accelerator,
    const std::string& command_name) {
  // On GTK, unlike Windows, the Event Targets contain all events but we must
  // only unregister the ones we registered targets for.
  if (!ShouldIgnoreCommand(command_name)) {
    gtk_accel_group_disconnect_key(
        accel_group_,
        ui::GetGdkKeyCodeForAccelerator(accelerator),
        ui::GetGdkModifierForAccelerator(accelerator));
  }
}

gboolean ExtensionKeybindingRegistryGtk::OnGtkAccelerator(
    GtkAccelGroup* group,
    GObject* acceleratable,
    guint keyval,
    GdkModifierType modifier) {
  ui::Accelerator accelerator = ui::AcceleratorForGdkKeyCodeAndModifier(
      keyval, modifier);

  return ExtensionKeybindingRegistry::NotifyEventTargets(accelerator);
}
