# Enhancing Macie data discovery capabilities with Textract as an overlay

This solution uses Amazon Textract as an additional conversion layer to convert image data into a JSON format that is supported by Macie. This enhancement effectively expends the coverage capabilities of what Macie can offer.


AWS Services used
- Application Composer - to generate baseline template and resources
- Amazon Textract
- Amazon Macie
- AWS Lambda
- Amazon Simple notification service
- Amazon DynamoDB
- Amazon S3
- Amazon EventBridge

Solution Architecture
![solution-architecture](/static/images/architecture-diagram.png)

## Prerequisites
In your own AWS environment, make sure that you have the following set up:

* Access and permission to deploy the related AWS services in CloudFormation shown below.


* [AWS SAM CLI installed](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/install-sam-cli.html). We will deploy the solution using AWS SAM. If you would like to understand more about how AWS SAM works and its specification, you can refer to this [documentation](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/sam-specification.html) that explains more in detail.

## Deployment steps
### Deploying the SAM template with AWS SAM CLI
1. Make sure that you have AWS SAM CLI installed. Otherwise, please [follow the steps here to install](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/install-sam-cli.html) the AWS SAM CLI.
2. Clone a copy of this repo. You can either deploy this by using CloudFormation or AWS SAM. The three Lambda Function source codes are in the `src` folder.
3. In your terminal, deploy the SAM template using `sam deploy --guided`. 
4. For Stack Name, you may give a new name (e.g. macie-enhanced).
5. Enter the AWS Region which you want to deploy this SAM template in.
6. For ExistingS3BucketName, if you have an existing S3 bucket which you want Macie to scan for sensitive data, key in the bucket name. Else, leave it blank and a new bucket will be created for you.
7. For MacieCustomIdRegex, enter the regex you want Macie to be scanning for in your confidential test files.
8. For EmailAddress, key in the email you wish to receive updates on completed Macie scans.
9. If you already have a Macie CloudWatch Log Group ('/aws/macie/classificationjobs') from your previous Macie scans, enter "Yes/y" for MacieLogGroupExists. Else, enter "No/n".
10. Follow through the other deployment steps and deploy the changeset created.
11. Check your email entered in step 8 to confirm the SNS subscription to receive notification when the Macie scan is done.

![sample-sam-deploy](/static/images/sample-sam-deploy.png)

### Testing out the Macie Enhanced scan
1. Go to the S3 console and select the bucket that starts with "s3-with-sensitive-data".
2. Upload one or more images with dummy sensitive information.
3. Go to the Lambda console and select the function with "TextractTriggerLambda" in its name.
4. Click into the "Test" tab, click the orange button "Test" to run the textract scan. The output will be automatically scanned by Macie using the custom data identifier created for you previously.
5. When the Macie scan of your object(s) is/are complete, you will receive an email notification.

![sample-macie-completed-sns](/static/images/sample-macie-completed-sns.png)

## Clean up the resources
To clean up the resources that you created for this example, follow the steps below:

1. To empty your S3 bucket, go to S3 and select for your bucket name starting with "s3-with-sensitive-data". Click “Empty" and follow the instruction on screen to empty it
2. Either (1) go to the CloudFormation console and delete the stack, or (2) run the following in your terminal to delete with AWS SAM CLI:
`sam delete`
3. Follow through the instruction on your terminal and select `y` when prompted for the decision to delete the stack.
