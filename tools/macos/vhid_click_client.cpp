#include <algorithm>
#include <cctype>
#include <chrono>
#include <condition_variable>
#include <cstdint>
#include <iostream>
#include <memory>
#include <mutex>
#include <sstream>
#include <stdexcept>
#include <string>
#include <thread>

#include <pqrs/dispatcher.hpp>
#include <pqrs/karabiner/driverkit/virtual_hid_device_driver.hpp>
#include <pqrs/karabiner/driverkit/virtual_hid_device_service.hpp>

namespace {

using Client = pqrs::karabiner::driverkit::virtual_hid_device_service::client;
using KeyboardInput = pqrs::karabiner::driverkit::virtual_hid_device_driver::hid_report::keyboard_input;
using KeyboardModifier = pqrs::karabiner::driverkit::virtual_hid_device_driver::hid_report::modifier;
using KeyboardParameters = pqrs::karabiner::driverkit::virtual_hid_device_service::virtual_hid_keyboard_parameters;
using PointingInput = pqrs::karabiner::driverkit::virtual_hid_device_driver::hid_report::pointing_input;

std::mutex state_mutex;
std::condition_variable state_changed;
bool pointing_ready = false;
bool keyboard_ready = false;
std::string startup_error;

void set_startup_error(const std::string& message) {
  std::lock_guard<std::mutex> lock(state_mutex);
  if (startup_error.empty()) {
    startup_error = message;
  }
  state_changed.notify_all();
}

void stop_client(std::unique_ptr<Client>& client) {
  if (client) {
    KeyboardInput release_keys;
    PointingInput release_report;
    client->async_post_report(release_keys);
    client->async_post_report(release_report);
    std::this_thread::sleep_for(std::chrono::milliseconds(50));
    client->async_stop();
    client.reset();
    std::this_thread::sleep_for(std::chrono::milliseconds(100));
  }
  pqrs::dispatcher::extra::terminate_shared_dispatcher();
}

bool keyboard_is_ready() {
  std::lock_guard<std::mutex> lock(state_mutex);
  if (!startup_error.empty()) {
    std::cout << "ERROR " << startup_error << std::endl;
    return false;
  }
  if (!keyboard_ready) {
    std::cout << "ERROR 虚拟键盘设备未就绪" << std::endl;
    return false;
  }
  return true;
}

bool read_unsigned(std::istringstream& input, unsigned int& value) {
  std::string token;
  if (!(input >> token) || token.empty() ||
      !std::all_of(token.begin(), token.end(), [](unsigned char ch) {
        return std::isdigit(ch) != 0;
      })) {
    return false;
  }
  try {
    value = static_cast<unsigned int>(std::stoul(token));
  } catch (const std::exception&) {
    return false;
  }
  return true;
}

int run() {
  pqrs::dispatcher::extra::initialize_shared_dispatcher();

  auto client = std::make_unique<Client>();
  client->connected.connect([&client] {
    client->async_virtual_hid_pointing_initialize();
    client->async_virtual_hid_keyboard_initialize(KeyboardParameters());
  });
  client->connect_failed.connect([](const auto& error_code) {
    set_startup_error("无法连接 Karabiner 虚拟 HID 服务: " + error_code.message());
  });
  client->error_occurred.connect([](const auto& error_code) {
    set_startup_error("Karabiner 虚拟 HID 服务错误: " + error_code.message());
  });
  client->virtual_hid_pointing_ready.connect([](bool ready) {
    std::lock_guard<std::mutex> lock(state_mutex);
    pointing_ready = ready;
    state_changed.notify_all();
  });
  client->virtual_hid_keyboard_ready.connect([](bool ready) {
    std::lock_guard<std::mutex> lock(state_mutex);
    keyboard_ready = ready;
    state_changed.notify_all();
  });
  client->driver_version_mismatched.connect([](bool mismatched) {
    if (mismatched) {
      set_startup_error("Karabiner 虚拟 HID 客户端与驱动版本不匹配");
    }
  });
  client->async_start();

  const auto startup_deadline = std::chrono::steady_clock::now() + std::chrono::seconds(10);
  {
    std::unique_lock<std::mutex> lock(state_mutex);
    state_changed.wait_until(lock, startup_deadline, [] {
      return pointing_ready || !startup_error.empty();
    });
    if (!pointing_ready) {
      const auto message = startup_error.empty()
                               ? "虚拟鼠标设备未就绪，请确认 Karabiner 虚拟 HID 驱动已安装并运行"
                               : startup_error;
      std::cout << "ERROR " << message << std::endl;
      lock.unlock();
      stop_client(client);
      return 1;
    }
    // 键盘没就绪也不要挡住鼠标。按键命令会单独返回错误。
    state_changed.wait_until(lock, startup_deadline, [] {
      return keyboard_ready || !startup_error.empty();
    });
  }

  std::cout << "READY" << std::endl;

  uint32_t buttons_state = 0;
  KeyboardInput keyboard_report;
  std::string line;
  while (std::getline(std::cin, line)) {
    if (line == "quit") {
      break;
    }

    std::istringstream input(line);
    std::string command;
    if (!(input >> command)) {
      std::cout << "ERROR 无效的虚拟鼠标命令" << std::endl;
      continue;
    }

    // 修饰键必须进 modifiers 位，不能当成键盘 usage 放进 keys。
    if (command == "key" || command == "mod") {
      std::string action;
      unsigned int value = 0;
      unsigned int duration_ms = 0;
      std::string trailing;
      if (!(input >> action)) {
        std::cout << "ERROR 无效的虚拟键盘命令" << std::endl;
        continue;
      }
      const bool is_tap = action == "tap";
      const bool is_down = action == "down";
      const bool is_up = action == "up";
      bool arguments_ok = is_tap || is_down || is_up;
      if (arguments_ok && is_tap) {
        arguments_ok = read_unsigned(input, value) && read_unsigned(input, duration_ms) &&
                       !(input >> trailing) && duration_ms >= 1 && duration_ms <= 60000;
      } else if (arguments_ok) {
        arguments_ok = read_unsigned(input, value) && !(input >> trailing);
      }
      const bool value_ok = command == "key"
                                ? value >= 1 && value <= 0x00ff
                                : value >= 1 && value <= 0x80 && (value & (value - 1)) == 0;
      if (!arguments_ok || !value_ok) {
        std::cout << "ERROR 无效的虚拟键盘命令" << std::endl;
        continue;
      }
      if (!keyboard_is_ready()) {
        continue;
      }

      const auto apply_key = [&keyboard_report, command, value](bool pressed) {
        if (command == "key") {
          const auto usage = static_cast<uint16_t>(value);
          if (pressed) {
            keyboard_report.keys.insert(usage);
          } else {
            keyboard_report.keys.erase(usage);
          }
          return;
        }
        const auto modifier = static_cast<KeyboardModifier>(value);
        if (pressed) {
          keyboard_report.modifiers.insert(modifier);
        } else {
          keyboard_report.modifiers.erase(modifier);
        }
      };
      const bool was_pressed = command == "key"
                                   ? keyboard_report.keys.exists(static_cast<uint16_t>(value))
                                   : keyboard_report.modifiers.exists(static_cast<KeyboardModifier>(value));
      apply_key(is_down || is_tap);
      client->async_post_report(keyboard_report);
      if (is_tap) {
        std::this_thread::sleep_for(std::chrono::milliseconds(duration_ms));
        if (!was_pressed) {
          apply_key(false);
          client->async_post_report(keyboard_report);
        }
      }
      std::cout << "OK" << std::endl;
      continue;
    }

    if (command == "move") {
      int dx = 0;
      int dy = 0;
      std::string trailing;
      if (!(input >> dx >> dy) || input >> trailing) {
        std::cout << "ERROR 无效的虚拟鼠标移动命令" << std::endl;
        continue;
      }

      {
        std::lock_guard<std::mutex> lock(state_mutex);
        if (!startup_error.empty() || !pointing_ready) {
          std::cout << "ERROR "
                    << (startup_error.empty() ? "虚拟鼠标设备已断开" : startup_error)
                    << std::endl;
          continue;
        }
      }

      PointingInput move_report;
      for (uint8_t report_button = 1; report_button <= 3; ++report_button) {
        if ((buttons_state & (1u << (report_button - 1))) != 0) {
          move_report.buttons.insert(report_button);
        }
      }
      const int clamped_dx = std::clamp(dx, -127, 127);
      const int clamped_dy = std::clamp(dy, -127, 127);
      move_report.x = static_cast<uint8_t>(static_cast<int8_t>(clamped_dx));
      move_report.y = static_cast<uint8_t>(static_cast<int8_t>(clamped_dy));
      client->async_post_report(move_report);
      std::cout << "OK" << std::endl;
      continue;
    }

    if (command == "wheel") {
      int vertical = 0;
      int horizontal = 0;
      std::string trailing;
      if (!(input >> vertical >> horizontal) || input >> trailing) {
        std::cout << "ERROR 无效的虚拟鼠标滚轮命令" << std::endl;
        continue;
      }

      {
        std::lock_guard<std::mutex> lock(state_mutex);
        if (!startup_error.empty() || !pointing_ready) {
          std::cout << "ERROR "
                    << (startup_error.empty() ? "虚拟鼠标设备已断开" : startup_error)
                    << std::endl;
          continue;
        }
      }

      PointingInput wheel_report;
      for (uint8_t report_button = 1; report_button <= 3; ++report_button) {
        if ((buttons_state & (1u << (report_button - 1))) != 0) {
          wheel_report.buttons.insert(report_button);
        }
      }
      const int clamped_v = std::clamp(vertical, -127, 127);
      const int clamped_h = std::clamp(horizontal, -127, 127);
      wheel_report.vertical_wheel = static_cast<uint8_t>(static_cast<int8_t>(clamped_v));
      wheel_report.horizontal_wheel = static_cast<uint8_t>(static_cast<int8_t>(clamped_h));
      client->async_post_report(wheel_report);
      std::cout << "OK" << std::endl;
      continue;
    }

    unsigned int button = 0;
    unsigned int duration_ms = 0;
    std::string trailing;
    if (!(input >> button >> duration_ms) ||
        input >> trailing ||
        (command != "click" && command != "press" && command != "release") ||
        (button < 1 || button > 3) ||
        (command == "click" && (duration_ms < 1 || duration_ms > 60000)) ||
        (command != "click" && duration_ms != 0)) {
      std::cout << "ERROR 无效的虚拟鼠标命令" << std::endl;
      continue;
    }

    {
      std::lock_guard<std::mutex> lock(state_mutex);
      if (!startup_error.empty() || !pointing_ready) {
        std::cout << "ERROR "
                  << (startup_error.empty() ? "虚拟鼠标设备已断开" : startup_error)
                  << std::endl;
        continue;
      }
    }

    const uint32_t button_mask = 1u << (button - 1);
    const bool was_pressed = (buttons_state & button_mask) != 0;
    if (command == "click" || command == "press") {
      buttons_state |= button_mask;
    } else {
      buttons_state &= ~button_mask;
    }

    PointingInput report;
    for (uint8_t report_button = 1; report_button <= 3; ++report_button) {
      if ((buttons_state & (1u << (report_button - 1))) != 0) {
        report.buttons.insert(report_button);
      }
    }
    client->async_post_report(report);

    if (command == "click") {
      std::this_thread::sleep_for(std::chrono::milliseconds(duration_ms));
      if (!was_pressed) {
        buttons_state &= ~button_mask;
      }

      PointingInput release_report;
      for (uint8_t report_button = 1; report_button <= 3; ++report_button) {
        if ((buttons_state & (1u << (report_button - 1))) != 0) {
          release_report.buttons.insert(report_button);
        }
      }
      client->async_post_report(release_report);
    }
    std::cout << "OK" << std::endl;
  }

  stop_client(client);
  return 0;
}

}

int main() {
  return run();
}
