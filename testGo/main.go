package main

import (
	"context"
	"database/sql"
	"fmt"
	"log"
	"os"
	"os/signal"
	"runtime"
	"strconv"
	"syscall"
	"testGO/custom_handler"
	"testGO/generated"
	"testGO/generated/users"
	"time"

	"entgo.io/ent/dialect"
	entsql "entgo.io/ent/dialect/sql"
	"github.com/gofiber/fiber/v2"
	"github.com/gofiber/fiber/v2/middleware/logger"
	"github.com/gofiber/fiber/v2/middleware/monitor"
	"github.com/gofiber/fiber/v2/middleware/recover"
	"github.com/google/uuid"
	_ "github.com/jackc/pgx/v5/stdlib"
)

type DataStore interface {
	Close() error
	GetClient() *generated.Client
}

type PostgresStore struct {
	db     *sql.DB
	client *generated.Client
}

func (p *PostgresStore) Close() error {
	return p.db.Close()
}

func (p *PostgresStore) GetClient() *generated.Client {
	return p.client
}

func DatabaseSession() (DataStore, error) {
	host := os.Getenv("DB_HOST")
	if host == "" {
		host = "bench_db"
	}

	port := 5432
	if portStr := os.Getenv("DB_PORT"); portStr != "" {
		if portNum, err := strconv.Atoi(portStr); err == nil {
			port = portNum
		}
	}

	user := os.Getenv("DB_USER")
	if user == "" {
		user = "postgres"
	}

	password := os.Getenv("DB_PASS")
	if password == "" {
		password = "CDC123"
	}

	dbname := os.Getenv("DB_NAME")
	if dbname == "" {
		dbname = "test"
	}

	dbDialect := os.Getenv("DB_DIALECT")
	if dbDialect == "" {
		dbDialect = "postgresql"
	}

	log.Printf("Connecting to database: %s://%s:***@%s:%d/%s",
		dbDialect, user, host, port, dbname)

	dsn := fmt.Sprintf(
		"%s://%s:%s@%s:%d/%s",
		dbDialect,
		user,
		password,
		host,
		port,
		dbname,
	)

	db, err := sql.Open("pgx", dsn)
	if err != nil {
		return nil, fmt.Errorf("Failed opening connection to database: %w", err)
	}

	// Connection pool settings
	db.SetMaxIdleConns(10)
	db.SetMaxOpenConns(15)
	db.SetConnMaxLifetime(time.Second * 1500)
	db.SetConnMaxIdleTime(time.Second * 300)

	// Test the connection
	if err := db.Ping(); err != nil {
		return nil, fmt.Errorf("Failed to ping database: %w", err)
	}

	drv := entsql.OpenDB(dialect.Postgres, db)
	client := generated.NewClient(generated.Driver(drv))

	return &PostgresStore{
		db:     db,
		client: client,
	}, nil
}

// Request and response structures
type UserCreateRequest struct {
	Name      string `json:"name"`
	FirstName string `json:"first_name"`
	LastName  string `json:"last_name"`
	IsActive  bool   `json:"is_active"`
}

type PetCreateRequest struct {
	Name     string `json:"name"`
	Type     string `json:"type"`
	IsActive bool   `json:"is_active"`
}

type PetResponse struct {
	ID       string `json:"id"`
	Name     string `json:"name"`
	Type     string `json:"type"`
	IsActive bool   `json:"is_active"`
}

type UserResponse struct {
	ID        string        `json:"id"`
	Name      string        `json:"name"`
	FirstName string        `json:"first_name"`
	LastName  string        `json:"last_name"`
	IsActive  bool          `json:"is_active"`
	Pets      []PetResponse `json:"pets"`
}

func main() {
	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer stop()

	store, err := DatabaseSession()
	if err != nil {
		log.Fatalf("Failed to initialize database: %v", err)
	}
	defer store.Close()

	client := store.GetClient()

	// Create schema if not exists
	if err := client.Schema.Create(ctx); err != nil {
		log.Fatalf("Failed creating schema resources: %v", err)
	}

	app := fiber.New(fiber.Config{
		AppName:               "Go Fiber API Benchmark",
		ErrorHandler:          custom_handler.New(),
		IdleTimeout:           5 * time.Second,
		ReadTimeout:           10 * time.Second,
		WriteTimeout:          10 * time.Second,
		DisableStartupMessage: false,
		BodyLimit:             10 * 1024 * 1024,
		Concurrency:           runtime.NumCPU() * 256,
		ReduceMemoryUsage:     true,
		StreamRequestBody:     true,
	})

	app.Use(recover.New())
	app.Use(logger.New())

	// Add monitor dashboard explicitly as a route handler (not middleware)
	app.Get("/metrics", monitor.New())

	// Create an API router with /api/v1 prefix
	api := app.Group("/api/v1")

	// 1. Create a user endpoint
	api.Post("/users", func(c *fiber.Ctx) error {
		startTime := time.Now()

		var req UserCreateRequest
		if err := c.BodyParser(&req); err != nil {
			return c.Status(fiber.StatusBadRequest).JSON(fiber.Map{
				"error": "Cannot parse JSON",
			})
		}

		user, err := client.Users.Create().
			SetName(req.Name).
			SetFirstName(req.FirstName).
			SetLastName(req.LastName).
			SetIsActive(req.IsActive).
			Save(ctx)

		if err != nil {
			log.Printf("Error creating user: %v", err)
			return c.Status(fiber.StatusInternalServerError).JSON(fiber.Map{
				"error": "Failed to create user",
			})
		}

		processingTime := time.Since(startTime)
		log.Printf("Create user processing time: %s", processingTime)

		return c.Status(fiber.StatusCreated).JSON(UserResponse{
			ID:        user.ID.String(),
			Name:      user.Name,
			FirstName: user.FirstName,
			LastName:  user.LastName,
			IsActive:  user.IsActive,
			Pets:      []PetResponse{},
		})
	})

	// 2. Add pet to user endpoint
	api.Post("/users/:id/pets", func(c *fiber.Ctx) error {
		startTime := time.Now()

		userID, err := uuid.Parse(c.Params("id"))
		if err != nil {
			return c.Status(fiber.StatusBadRequest).JSON(fiber.Map{
				"error": "Invalid user ID",
			})
		}

		// Check if user exists
		exists, err := client.Users.Query().
			Where(users.ID(userID)).
			Exist(ctx)

		if err != nil {
			log.Printf("Error checking user existence: %v", err)
			return c.Status(fiber.StatusInternalServerError).JSON(fiber.Map{
				"error": "Database error",
			})
		}

		if !exists {
			return c.Status(fiber.StatusNotFound).JSON(fiber.Map{
				"error": "User not found",
			})
		}

		var req PetCreateRequest
		if err := c.BodyParser(&req); err != nil {
			return c.Status(fiber.StatusBadRequest).JSON(fiber.Map{
				"error": "Cannot parse JSON",
			})
		}

		user, err := client.Users.Get(ctx, userID)
		if err != nil {
			log.Printf("Error getting user: %v", err)
			return c.Status(fiber.StatusInternalServerError).JSON(fiber.Map{
				"error": "Failed to get user",
			})
		}

		pet, err := client.Pets.Create().
			SetOwner(user).
			SetUserID(userID).
			SetName(req.Name).
			SetType(req.Type).
			SetIsActive(req.IsActive).
			Save(ctx)

		if err != nil {
			log.Printf("Error creating pet: %v", err)
			return c.Status(fiber.StatusInternalServerError).JSON(fiber.Map{
				"error": "Failed to create pet",
			})
		}

		processingTime := time.Since(startTime)
		log.Printf("Add pet to user processing time: %s", processingTime)

		return c.Status(fiber.StatusCreated).JSON(PetResponse{
			ID:       pet.ID.String(),
			Name:     pet.Name,
			Type:     pet.Type,
			IsActive: pet.IsActive,
		})
	})

	// 3. Get user with pets endpoint
	api.Get("/users/:id", func(c *fiber.Ctx) error {
		startTime := time.Now()

		userID, err := uuid.Parse(c.Params("id"))
		if err != nil {
			return c.Status(fiber.StatusBadRequest).JSON(fiber.Map{
				"error": "Invalid user ID",
			})
		}

		user, err := client.Users.Query().
			Where(users.ID(userID)).
			WithPets().
			Only(ctx)

		if err != nil {
			if generated.IsNotFound(err) {
				return c.Status(fiber.StatusNotFound).JSON(fiber.Map{
					"error": "User not found",
				})
			}
			log.Printf("Error fetching user: %v", err)
			return c.Status(fiber.StatusInternalServerError).JSON(fiber.Map{
				"error": "Database error",
			})
		}

		var petResponses []PetResponse
		for _, pet := range user.Edges.Pets {
			petResponses = append(petResponses, PetResponse{
				ID:       pet.ID.String(),
				Name:     pet.Name,
				Type:     pet.Type,
				IsActive: pet.IsActive,
			})
		}

		processingTime := time.Since(startTime)
		log.Printf("Get user with pets processing time: %s", processingTime)

		return c.Status(fiber.StatusOK).JSON(UserResponse{
			ID:        user.ID.String(),
			Name:      user.Name,
			FirstName: user.FirstName,
			LastName:  user.LastName,
			IsActive:  user.IsActive,
			Pets:      petResponses,
		})
	})

	// Health check endpoint
	api.Get("/health", func(c *fiber.Ctx) error {
		return c.Status(fiber.StatusOK).JSON(fiber.Map{
			"status":    "ok",
			"timestamp": time.Now().Unix(),
		})
	})

	// Start the server in a separate goroutine
	go func() {
		if err := app.Listen(":8080"); err != nil {
			log.Printf("Server error: %v", err)
		}
	}()

	log.Println("Server started on :8080")

	// Wait for termination signal
	<-ctx.Done()
	log.Println("Shutting down gracefully...")

	// Give server 5 seconds to gracefully shut down
	shutdownCtx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	if err := app.ShutdownWithContext(shutdownCtx); err != nil {
		log.Printf("Server shutdown error: %v", err)
	}
}
