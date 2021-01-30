import os
import json
import datetime

from webcam.constants import *
from webcam.utils import log, log_error
from webcam.system import System
from webcam.configuration import Configuration
from webcam.server import Server
from webcam.camera import Camera


def main():
    """
    Main script coordinating all operations.
    """
    print("\n==========================================\n")
    log("Start")

    try:
        # Initial setup
        start = datetime.datetime.now()
        errors_were_raised = False

        system = System()
        status = system.report_general_status()  # TODO this can check if it's online and switch
                                                 #  to offline mode if not (issue #7)
        log("Status report:")
        for key, value in status.items():
            log(f" - {key}: {value}")

        try:
            initial_configuration = Configuration()
        except Exception as e:
            log_error(f"Failed to load the initial configuration from {CONFIGURATION_PATH}", 
                      e, fatal="cannot proceed without any data. Exiting.")
            raise RuntimeError(e)

        # Verify if we're into the active hours or not, if defined
        try:
            if not initial_configuration.is_active_hours():
                log("The current time is outside working hours. Turning off.")
                return
        except Exception as e:
            log_error("An error occurred trying to assess if the current time is within active hours. " +
                      "Assuming YES.", e)
        log("The current time is inside active hours. Proceeding.")

        initial_server = Server(initial_configuration.server)

        # Getting the new configuration from the server
        try:
            configuration = initial_server.update_configuration(initial_configuration)

        except Exception as e:
            log_error("Something went wrong fetching the new configuration file "
                      "from the server.", e)
            log("Falling back to the old configuration.")
            errors_were_raised = True
            configuration = initial_configuration

        log("Configuration in use:")
        print(configuration)

        # Re-initialize the server
        server = Server(configuration.server)

        # Send logs of the previous run
        server.upload_logs()

        # Update the system to conform to the new configuration file
        try:
            system.apply_system_settings(configuration)
        except Exception as e:
            log_error("Something happened while applying the system "
                "settings from the new configuration file.", e)
            errors_were_raised = True
            log("Re-applying the old system configuration.")
            log("+++++++++++++++++++++++++++++++++++++++++++")
            try:
                system.apply_system_settings(initial_configuration)
            except Exception as e:
                log_error("Something unexpected occurred while re-applying the "
                    "old system settings!", e,
                    fatal="the webcam might be in an inconsistent state." +
                    "ZANZOCAM might need manual intervention at this point.")
            log("+++++++++++++++++++++++++++++++++++++++++++")

        # Create the picture
        try:
            camera = Camera(configuration)
            camera.take_picture()

        except Exception as e:
            # Try again using the old config file
            log_error("An error occurred while taking the picture.", e)
            new_configuration_raised_exception = True
            log("Trying again with the old configuration.")
            log("+++++++++++++++++++++++++++++++++++++++++++")
            camera = Camera(initial_configuration)
            camera.take_picture()
            log("+++++++++++++++++++++++++++++++++++++++++++")
            return

            # That's the second run that failed: give up.
            log_error("Something happened while running with the old configuration file too!", e,
                        fatal="Exiting.")
            raise RuntimeError(e)
            
        # Send the picture
        try:
            if os.path.exists(PATH / camera.processed_image_name):
                server.upload_picture(camera.processed_image_name, camera.processed_image_path)
                camera.clean_up()
        except Exception as e:
            log_error("Something happened uploading the picture! It was "+
                      "probably not sent", e,
                      fatal="The error was unexpected, can't fix. The picture won't be uploaded.")
            raise RuntimeError(e)
    
    # Catch expected fatal errors
    except RuntimeError as re:
        log("A fatal error occurred during the main procedure.")
        errors_were_raised = True

    # Catch unexpected fatal errors
    except Exception as e:
        errors_were_raised = True
        log_error("Something unexpected occurred while running the main procedure.", 
                  e, fatal="Exiting.")
        
    # Print the completion time anyway
    finally:
        # If we had trouble with the new config, restore the old from the backup
        # TODO assess the situation better! Maybe the failure is unrelated.
        errors_were_raised_str = "successfully"
        if errors_were_raised:
            initial_configuration.restore_backup()
            initial_server.upload_failure_report(configuration.server, initial_configuration.server)
            errors_were_raised_str = "with errors"
            
        end = datetime.datetime.now()
        log(f"Execution completed {errors_were_raised_str} in: {end - start}")
        print("\n==========================================\n")




if "__main__" == __name__:
    main()

