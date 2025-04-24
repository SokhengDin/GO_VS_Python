package custom_handler

import (
	"github.com/gofiber/fiber/v2"
)

func New() fiber.ErrorHandler {

	return func(c *fiber.Ctx, err error) error {

		code := fiber.StatusInternalServerError
		message := "Internal Server Error"

		if e, ok := err.(*fiber.Error); ok {
			code = e.Code
			message = e.Message
		} else {
			message = "Internal Server Error"
		}

		if code < 500 {
			message = err.Error()
		}

		return c.Status(code).JSON(fiber.Map{
			"status":  code,
			"message": message,
		})
	}
}
