% PCoA: Principal coordinates analysis of a distance matrix.  Eigenvector 
%       coefficients represent coordinates of objects.
%
%     Usage: [evects,evals] = pcoa(dist)
%
%       dist =   [n x n] square symmetric distance matrix.
%       ---------------------------------------------------------------
%       evects = [n x k] matrix of eigenvectors (columns), individually 
%                   normalized to sum of squares = eigenvalue, for the
%                   k positive eigenvalues.
%       evals =  [k x 1] vector of k positive eigenvalues.
%

% Krzanowski and Marriott (1994), pp. 108-109.

% RE Strauss, 6/3/95

function [evects,evals] = pcoa(dist)
  n = size(dist,1);

  gamma = zeros(n);                   % Form gamma matrix
  for i=1:(n-1)
    for j=(i+1):n
      gamma(i,j) = -0.5 * dist(i,j)^2;
      gamma(j,i) = gamma(i,j);
    end;
  end;

  mean_col = mean(gamma);             % Convert to phi matrix
  mean_gamma = mean(mean_col);
  phi = gamma;
  for i=1:n
    mean_row = mean(gamma(i,:));
    for j=1:n
      phi(i,j) = gamma(i,j) - mean_row - mean_col(j) + mean_gamma;
    end;
  end;

  [evects,evals] = eigen(phi);         % Eigenanalysis

  k = max(find(evals>0));              % Number of positive eigenvalues
  evals = evals(1:k);                  % Adjust matrix sizes
  evects = evects(:,1:k);

  for i=1:k                            % Normalize eigenvectors
    f = evals(i)/sum(evects(:,i).^2);
    evects(:,i) = sqrt((evects(:,i).^2).*f).*sign(evects(:,i));
  end;  

  return;
